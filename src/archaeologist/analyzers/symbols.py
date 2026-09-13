"""Symbol extraction via Tree-sitter (optional dependency).

If `tree_sitter` and a language grammar are not installed, symbol features
degrade to unavailable; every other command keeps working. Symbols are best
effort: kinds and line ranges only, no name resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..walker import RepoFile, MAX_FILE_BYTES

try:
    from tree_sitter import Language, Parser
    HAS_TS = True
except ImportError:
    HAS_TS = False


@dataclass
class Symbol:
    name: str
    kind: str          # function / class / struct / enum / method / trait / impl
    file: str          # repo-relative
    start_line: int    # 1-based, inclusive
    end_line: int      # 1-based, inclusive
    language: str
    parent: str | None = None
    children: list["Symbol"] = field(default_factory=list)


# node type -> (kind, name field)
NODE_KINDS = {
    "python": {
        "function_definition": ("function", "name"),
        "class_definition": ("class", "name"),
    },
    "c": {
        "function_definition": ("function", "declarator"),
        "struct_specifier": ("struct", "name"),
        "enum_specifier": ("enum", "name"),
    },
    "cpp": {
        "function_definition": ("function", "declarator"),
        "struct_specifier": ("struct", "name"),
        "class_specifier": ("class", "name"),
        "enum_specifier": ("enum", "name"),
    },
    "rust": {
        "function_item": ("function", "name"),
        "struct_item": ("struct", "name"),
        "enum_item": ("enum", "name"),
        "trait_item": ("trait", "name"),
        "impl_item": ("impl", "type"),
    },
    "javascript": {
        "function_declaration": ("function", "name"),
        "class_declaration": ("class", "name"),
        "method_definition": ("method", "name"),
    },
    "go": {
        "function_declaration": ("function", "name"),
        "method_declaration": ("method", "name"),
    },
}

# grammar package + language name per our language display names
GRAMMARS: dict[str, tuple[str, str]] = {
    "Python": ("tree_sitter_python", "python"),
    "C": ("tree_sitter_c", "c"),
    "C++": ("tree_sitter_cpp", "cpp"),
    "C/C++ Header": ("tree_sitter_cpp", "cpp"),
    "Rust": ("tree_sitter_rust", "rust"),
    "JavaScript": ("tree_sitter_javascript", "javascript"),
    "Go": ("tree_sitter_go", "go"),
}

_parser_cache: dict[str, "Parser"] = {}


def get_parser(lang_name: str):
    if not HAS_TS:
        return None
    if lang_name in _parser_cache:
        return _parser_cache[lang_name]
    if lang_name not in GRAMMARS:
        return None
    module_name, grammar_name = GRAMMARS[lang_name]
    try:
        import importlib
        mod = importlib.import_module(module_name)
        parser = Parser(Language(mod.language()))
    except (ImportError, Exception):
        return None
    _parser_cache[lang_name] = parser
    return parser


def extract_symbols(lang_name: str, rel: str, text: str) -> list[Symbol]:
    parser = get_parser(lang_name)
    if parser is None:
        return []
    kinds = NODE_KINDS.get(GRAMMARS[lang_name][1], {})
    if not kinds:
        return []
    tree = parser.parse(text.encode("utf-8", errors="replace"))
    symbols: list[Symbol] = []
    stack: list[Symbol] = []

    def visit(node):
        kind_field = kinds.get(node.type)
        if kind_field is not None:
            kind, name_field = kind_field
            name_node = node.child_by_field_name(name_field)
            name = _render_name(name_node) if name_node else None
            if name:
                sym = Symbol(
                    name=name, kind=kind, file=rel,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    language=lang_name,
                    parent=stack[-1].name if stack and stack[-1].kind in ("class", "impl") else None,
                )
                if stack:
                    stack[-1].children.append(sym)
                else:
                    symbols.append(sym)
                stack.append(sym)
                for child in node.children:
                    visit(child)
                stack.pop()
                return
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return symbols


def _render_name(node) -> str | None:
    """Render a name node; for C/C++ function declarators dig out the identifier."""
    if node.type == "identifier" or node.type == "type_identifier":
        return node.text.decode("utf-8", errors="replace")
    for child in node.children:
        if child.type in ("identifier", "field_identifier", "function_declarator",
                          "pointer_declarator", "type_identifier"):
            got = _render_name(child)
            if got:
                return got
    # fallback: first identifier inside
    for child in node.children:
        got = _render_name(child)
        if got:
            return got
    return None


def index_symbols(files: list[RepoFile], root: Path,
                  max_files: int = 20000) -> list[Symbol]:
    """Build a flat symbol list across the repository (top-level symbols,
    with methods nested under their classes)."""
    if not HAS_TS:
        return []
    out: list[Symbol] = []
    count = 0
    for f in files:
        if count >= max_files:
            break
        if f.binary or f.language not in GRAMMARS or f.size > MAX_FILE_BYTES:
            continue
        try:
            text = f.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        count += 1
        out.extend(extract_symbols(f.language, f.rel, text))
    return out


def find_symbols(symbols: list[Symbol], query: str) -> list[Symbol]:
    """Match a symbol by exact name (first), then unique-suffix, then prefix."""
    q = query.lower()
    exact = [s for s in symbols if s.name.lower() == q]
    if exact:
        return exact
    suffix = [s for s in symbols if s.name.lower().endswith("::" + q) or s.name.lower() == q]
    if suffix:
        return suffix
    return [s for s in symbols if s.name.lower().startswith(q)][:10]


def referenced_by(root: Path, matches: list[Symbol],
                  files: list[RepoFile], max_scan: int = 4000) -> dict[tuple[str, str], list[str]]:
    """Text-level reference map: which other files mention each symbol name.

    Deliberately coarse (no name resolution); presented as 'text-level' in
    output so the confidence is explicit."""
    names = {s.name for s in matches}
    result: dict[tuple[str, str], list[str]] = {}
    per_file: dict[str, set[str]] = {}
    count = 0
    for f in files:
        if count >= max_scan:
            break
        if f.binary or f.language is None or f.size > MAX_FILE_BYTES:
            continue
        try:
            text = f.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        count += 1
        hits = {n for n in names if n in text}
        if hits:
            per_file[f.rel] = hits
    for s in matches:
        users = [rel for rel, hits in sorted(per_file.items())
                 if s.name in hits and rel != s.file]
        result[(s.file, s.name)] = users
    return result
