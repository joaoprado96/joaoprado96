#!/usr/bin/env python3
"""
claude_indexer.py v2 - INDEXADOR GLOBAL para projetos Kotlin (e Java misto) + Claude Code.

Um unico arquivo, so biblioteca padrao (Python 3.9+). Copie para qualquer projeto (ou deixe em
~/tools) e rode:

  python claude_indexer.py [RAIZ]              indexa (padrao: pasta atual)
  python claude_indexer.py index --check       CI: falha (exit 1) se o indice estiver desatualizado
  python claude_indexer.py watch               reindexa ao detectar mudancas
  python claude_indexer.py workspace PASTA     descobre e indexa varios projetos de uma pasta
  python claude_indexer.py query <cmd> ...     consulta o grafo (find, show, callers, callees, impl,
                                               uses, impact, path, deps, file, tree, endpoints,
                                               cycles, hotspots, dead, stats)

O que faz: lexer/parser Kotlin de verdade (strings, comentarios aninhados, KDoc, generics,
extensoes, companions, enums, membros aninhados), Java em nivel de tipos/metodos, modulos
Gradle/Maven (+ version catalog), grafo (imports, heranca, chamadas, instanciacao, injecao,
overrides), SQLite consultavel, ciclos (Tarjan), codigo morto, god classes, complexidade,
violacoes de camada, endpoints/listeners/jobs, fluxos ponta a ponta, arvore completa, mermaid,
CLAUDE.md por projeto/modulo preservando trechos manuais e uma Skill para o Claude consultar o
indice em vez de ler arquivos (economia de tokens).

Config opcional: .claude-indexer.json (raiz) e ~/.claude-indexer.json (global). Ignore extra:
.claude-indexer-ignore (um padrao por linha, estilo gitignore simplificado).
"""
from __future__ import annotations

import argparse
import contextlib
import fnmatch
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, TypedDict

VERSION = "2.0"
# Incrementar sempre que extract_refs, resolve_call, resolve_field ou o formato de
# syms/calls/fields mudar (invalida o cache.json). NAO e necessario para mudancas em LAYERS,
# entry_interfaces ou qualquer heuristica que rode em cima do "data" ja cacheado.
PARSER_VERSION = 13

# =========================================================================== #
# Constantes
# =========================================================================== #
GENERATED_HINTS = ("/generated/", "/build/generated/", "/gen/", "/.cxx/")
GENERATED_FILE_NAMES = {"R.kt", "R.java", "BuildConfig.kt", "BuildConfig.java", "Manifest.java"}
DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".gradle", ".idea", ".vscode", ".kotlin", "build", "out", "bin",
    "node_modules", "target", "__pycache__", ".venv", "venv", "dist", ".claude", ".mvn",
    ".settings", ".metadata",
}
BINARY_SUFFIXES = {
    ".class", ".jar", ".war", ".ear", ".zip", ".gz", ".tar", ".7z", ".png", ".jpg", ".jpeg", ".gif",
    ".ico", ".pdf", ".log", ".lock", ".exe", ".dll", ".so", ".dylib", ".bin", ".db", ".sqlite",
    ".dump", ".bak", ".jks", ".p12", ".woff", ".woff2", ".ttf", ".mp4", ".mov", ".keystore",
}
SOURCE_EXTS = {".kt": "kt", ".kts": "kts", ".java": "java"}
MAX_BYTES = 2_000_000
STATE_DIR = ".claude/index"
DOCS_DIR = "docs"
AUTO_START = "<!-- AUTO:START - gerado por claude_indexer.py; edite fora deste bloco -->"
AUTO_END = "<!-- AUTO:END -->"
GEN_MARK = "<!-- gerado por claude_indexer.py -->"

MODS = {
    "public", "private", "protected", "internal", "open", "final", "abstract", "sealed", "data",
    "enum", "annotation", "value", "inline", "noinline", "crossinline", "inner", "companion",
    "override", "lateinit", "const", "suspend", "operator", "infix", "tailrec", "external",
    "expect", "actual", "vararg", "reified",
}
JAVA_MODS = {
    "public", "private", "protected", "static", "final", "abstract", "synchronized", "native",
    "transient", "volatile", "strictfp", "default", "sealed",
}
KEYWORDS = {
    "if", "else", "for", "while", "do", "when", "try", "catch", "finally", "return", "throw",
    "break", "continue", "fun", "val", "var", "class", "object", "interface", "in", "is", "as",
    "super", "this", "null", "true", "false", "package", "import", "init", "constructor", "by",
    "where", "new", "instanceof", "switch", "case", "synchronized", "assert",
}
USE_SITES = {"file", "get", "set", "field", "param", "property", "receiver", "setparam", "delegate"}
COROUTINE_TYPES = {"Flow", "StateFlow", "SharedFlow", "Deferred"}  # kotlinx.coroutines, sempre
                                                                    # ativo (nao e lib trocavel
                                                                    # como Mono/Flux em reactive_wrappers)
COROUTINE_BUILDERS = {"launch", "async", "withContext", "runBlocking", "coroutineScope", "supervisorScope"}
COROUTINE_TYPE_SIGNALS = {"Dispatchers", "CoroutineScope", "CoroutineContext"}
# Operadores que so existem em Flow/Reactor, nunca em List/Sequence/Iterable do Kotlin -- usados
# como "gatilho" pra reconhecer uma cadeia como pipeline reativa (ver _reconstruct_pipeline).
REACTIVE_OPS_EXCLUSIVE = {
    "catch", "retry", "retryWhen", "flatMapMerge", "flatMapConcat", "flatMapLatest", "switchMap",
    "concatMap", "debounce", "distinctUntilChanged", "collectLatest", "stateIn", "shareIn",
    "flowOn", "subscribeOn", "publishOn", "doOnNext", "doOnError", "doOnComplete",
    "doOnSubscribe", "onErrorResume", "onErrorReturn", "onErrorContinue", "sample",
}
# Ambiguos: tambem existem em List/Sequence comuns -- so contam pro relatorio se a MESMA
# cadeia ja tiver pelo menos um operador exclusivo (evita falso positivo em list.map{}.filter{}).
REACTIVE_OPS_AMBIGUOUS = {
    "map", "filter", "flatMap", "onEach", "reduce", "scan", "take", "drop", "zip", "first",
    "firstOrNull", "toList", "collect", "subscribe",
}
HTTP_VERBS = {"get": "GET", "post": "POST", "put": "PUT", "delete": "DELETE", "patch": "PATCH",
              "head": "HEAD", "options": "OPTIONS"}
COMMON_NAMES = {
    "get", "set", "map", "let", "apply", "also", "run", "toString", "equals", "hashCode", "forEach",
    "filter", "add", "remove", "put", "size", "isEmpty", "first", "last", "with", "use", "invoke",
    "copy", "close", "build", "create", "of", "from", "to", "plus", "minus", "contains", "find",
    "load", "save", "delete", "update", "execute", "process", "handle", "apply", "test", "init",
}
OPEN, CLOSE = {"(": ")", "{": "}", "[": "]"}, {")", "}", "]"}
CLOSE_OPEN = {v: k for k, v in OPEN.items()}
CONT_PREV = {".", "?.", "?:", "&&", "||", "+", "-", "*", "/", "%", "=", ",", "(", "[", "{", "->", "::",
             "<", "!", ":", "==", "!=", "===", "!==", "..", "+=", "-=", "*=", "/=", "%="}
CONT_PREV_ID = {"by", "is", "in", "as", "else", "if", "when", "return", "throw", "new"}
CONT_NEXT = {".", "?.", "?:", "&&", "||", "+", "-", "*", "/", "%", "->", ":", "?", "!!", "==", "!=",
             "===", "!==", "as", "is", "in", "else", "..", "::", ")", "]", "}"}
TYPE_CONT_PREV = {".", ",", "<", "(", "->", "&", ":", "?.", "["}
TYPE_CONT_NEXT = {".", "?", "->", "&", ")", ">", ",", "]", "?.", "<"}
MULTI3 = {"===", "!=="}
MULTI2 = {"->", "::", "?.", "?:", "&&", "||", "..", "!!", "==", "!=", "+=", "-=", "*=", "/=", "%=", "++", "--"}

LAYERS = [  # (camada, anotacoes, sufixos, trechos de pacote)
    ("controller", {"RestController", "Controller", "Path", "RequestMapping"}, ("Controller", "Resource", "Router", "Routes"), (".controller.", ".web.", ".api.", ".rest.", ".routes.")),
    ("job", {"Scheduled", "EnableBatchProcessing", "KafkaListener", "RabbitListener", "JmsListener", "SqsListener"}, ("Job", "Step", "Tasklet", "Reader", "Writer", "Processor", "Migrator", "Migration", "Listener", "Consumer", "Worker", "Handler"), (".job.", ".jobs.", ".batch.", ".migration.", ".listener.", ".consumer.", ".handler.", ".handlers.")),
    ("service", {"Service"}, ("Service", "UseCase", "Interactor", "Facade", "Manager"), (".service.", ".services.", ".usecase.", ".application.", ".domain.service.")),
    ("repository", {"Repository"}, ("Repository", "Dao", "Gateway", "Store"), (".repository.", ".repositories.", ".dao.", ".persistence.")),
    ("entity", {"Entity", "Table", "Document", "MappedSuperclass", "Embeddable"}, ("Entity",), (".entity.", ".entities.", ".domain.model.", ".model.")),
    ("config", {"Configuration", "ConfigurationProperties", "EnableAutoConfiguration", "SpringBootApplication"}, ("Config", "Configuration", "Properties", "Module", "Application"), (".config.", ".configuration.")),
    ("client", {"FeignClient"}, ("Client", "Adapter", "Api", "Integration"), (".client.", ".clients.", ".integration.", ".adapter.", ".infra.")),
    ("mapper", {"Mapper"}, ("Mapper", "Converter", "Transformer", "Assembler"), (".mapper.", ".mappers.", ".converter.")),
    ("dto", set(), ("Dto", "DTO", "Request", "Response", "Event", "Command", "Query", "Payload", "Input", "Output", "Message"), (".dto.", ".dtos.", ".payload.", ".event.", ".events.")),
    ("exception", set(), ("Exception", "Error"), (".exception.", ".exceptions.", ".error.")),
    ("util", set(), ("Utils", "Util", "Helper", "Helpers", "Extensions", "Ext"), (".util.", ".utils.", ".common.", ".shared.")),
]
DEFAULT_FORBID = [["controller", "repository"], ["repository", "controller"], ["repository", "service"],
                  ["entity", "service"], ["entity", "controller"], ["entity", "repository"],
                  ["dto", "service"], ["dto", "controller"], ["dto", "repository"]]
TECH_BY_IMPORT = {
    "org.springframework.boot": "Spring Boot", "org.springframework.batch": "Spring Batch",
    "org.springframework.web": "Spring Web", "org.springframework.data": "Spring Data",
    "org.springframework.kafka": "Spring Kafka", "org.springframework.cloud": "Spring Cloud",
    "io.ktor": "Ktor", "io.micronaut": "Micronaut", "io.quarkus": "Quarkus", "io.vertx": "Vert.x",
    "org.jetbrains.exposed": "Exposed", "org.jooq": "jOOQ", "javax.persistence": "JPA",
    "jakarta.persistence": "JPA", "org.hibernate": "Hibernate", "org.flywaydb": "Flyway",
    "org.liquibase": "Liquibase", "liquibase": "Liquibase", "org.apache.kafka": "Kafka",
    "com.rabbitmq": "RabbitMQ", "org.springframework.amqp": "RabbitMQ", "kotlinx.coroutines": "Coroutines",
    "kotlinx.serialization": "kotlinx.serialization", "com.fasterxml.jackson": "Jackson",
    "org.junit": "JUnit", "io.kotest": "Kotest", "io.mockk": "MockK", "org.mockito": "Mockito",
    "org.testcontainers": "Testcontainers", "io.github.oshai.kotlinlogging": "kotlin-logging",
    "org.slf4j": "SLF4J", "io.micrometer": "Micrometer", "com.zaxxer.hikari": "HikariCP",
    "org.koin": "Koin", "dagger": "Dagger", "javax.inject": "JSR-330", "jakarta.inject": "JSR-330",
    "com.google.gson": "Gson", "retrofit2": "Retrofit", "okhttp3": "OkHttp", "androidx": "AndroidX",
    "org.apache.poi": "Apache POI", "com.amazonaws": "AWS SDK", "software.amazon": "AWS SDK v2",
}
DEFAULT_CONFIG = {
    "ignore": [], "docs_dir": DOCS_DIR, "state_dir": STATE_DIR, "project_name": "",
    "god_class_loc": 500, "god_class_members": 40, "cc_threshold": 15, "long_fun_loc": 80,
    "many_params": 7, "tree_max_files_per_dir": 300, "flow_depth": 5, "max_flows": 80,
    "flow_fanout": 10, "forbid": DEFAULT_FORBID, "layers": [], "entry_annotations": [], "entry_interfaces": [],
    "reactive_wrappers": [],
    "dead_ignore_annotations": [], "max_dead": 80, "min_call_conf": 0.4, "module_claude_md": True,
    "write_settings": True, "write_skill": True, "workers": 0,
}


# =========================================================================== #
# Saida (avisos/erros/progresso) — unico ponto de contato com stderr
# =========================================================================== #
def warn(msg: str) -> None:
    print(f"[aviso] {msg}", file=sys.stderr)


def err(msg: str) -> None:
    print(f"[erro] {msg}", file=sys.stderr)


class ProgressTicker:
    """Heartbeat de uma etapa longa (uma linha, sobrescrita via \\r). Silencioso se --quiet, sem
    tty ou se o total nao for grande o bastante para justificar o ruido."""

    def __init__(self, prefix: str, total: int, *, quiet: bool, min_total: int = 20, interval: float = 0.5):
        self.prefix, self.total, self.interval = prefix, total, interval
        self.active = total >= min_total and not quiet and sys.stderr.isatty()
        self.last = 0.0

    def tick(self, done: int) -> None:
        if not self.active:
            return
        now = time.time()
        if now - self.last < self.interval and done < self.total:
            return
        self.last = now
        print(f"\r{self.prefix} {done}/{self.total}...", end="", file=sys.stderr, flush=True)

    def done(self) -> None:
        if self.active:
            print(file=sys.stderr)


# =========================================================================== #
# Lexer
# =========================================================================== #
_ID = re.compile(r"(?:[^\W\d]|\$)[\w$]*")
_NUM = re.compile(r"\d[\w]*(?:\.\d[\w]*)?")
_BC = re.compile(r"/\*|\*/")
_INTERP_CALL = re.compile(r"(?<!\\)\$\{\s*([A-Za-z_]\w*(?:\?\.[A-Za-z_]\w*|\.[A-Za-z_]\w*)*)\s*\(")
_LAMBDA_RECV = re.compile(r"^([\w.]+)\??\.\(.*\)\s*->")


def _skip_block_comment(src: str, i: int) -> int:
    depth = 0
    for m in _BC.finditer(src, i):
        if m.group() == "/*":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return m.end()
    return len(src)


def _skip_template(src: str, i: int) -> int:
    depth, n = 1, len(src)
    while i < n:
        c = src[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        elif c == '"':
            if src.startswith('"""', i):
                j = src.find('"""', i + 3)
                i = n if j < 0 else j + 3
            else:
                i = _skip_string(src, i)
            continue
        elif c == "'":
            i = min(n, (src.find("'", i + 2) + 1 or n) if src[i + 1:i + 2] == "\\" else i + 3)
            continue
        i += 1
    return n


def _skip_string(src: str, i: int) -> int:
    n = len(src)
    i += 1
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i + 1
        if c == "$" and src[i + 1:i + 2] == "{":
            i = _skip_template(src, i + 2)
            continue
        if c == "\n":
            return i
        i += 1
    return n


def lex(src: str) -> list:
    """Tokens: (kind, text, line, kdoc). kind: id | sym | str | num | chr."""
    toks: list = []
    append = toks.append
    i, n, line = 0, len(src), 1
    doc = None
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r\f\v\ufeff":
            i += 1
            continue
        if c == "/":
            nx = src[i + 1:i + 2]
            if nx == "/":
                j = src.find("\n", i)
                i = n if j < 0 else j
                continue
            if nx == "*":
                j = _skip_block_comment(src, i)
                if src.startswith("/**", i) and not src.startswith("/**/", i):
                    doc = src[i:j]
                line += src.count("\n", i, j)
                i = j
                continue
        if c == '"':
            if src.startswith('"""', i):
                j = src.find('"""', i + 3)
                if j < 0:
                    j = max(i + 3, n - 3)
                while src.startswith('"', j + 3):
                    j += 1
                end, val = min(n, j + 3), src[i + 3:j]
            else:
                end = _skip_string(src, i)
                val = src[i + 1:end - 1]
            append(("str", val[:200], line, doc))
            doc = None
            line += src.count("\n", i, end)
            i = end
            continue
        if c == "'":
            if src[i + 1:i + 2] == "\\":
                j = src.find("'", i + 2)
                end = n if j < 0 else j + 1
            else:
                end = min(i + 3, n)
            append(("chr", "c", line, doc))
            doc = None
            i = end
            continue
        if c == "`":
            j = src.find("`", i + 1)
            j = n if j < 0 else j
            append(("id", src[i + 1:j], line, doc))
            doc = None
            i = j + 1
            continue
        if c.isalpha() or c == "_" or c == "$":
            m = _ID.match(src, i)
            if m:
                append(("id", m.group(), line, doc))
                doc = None
                i = m.end()
                continue
        if c.isdigit():
            m = _NUM.match(src, i)
            append(("num", m.group(), line, doc))
            doc = None
            i = m.end()
            continue
        tri, duo = src[i:i + 3], src[i:i + 2]
        if tri in MULTI3:
            append(("sym", tri, line, doc))
            i += 3
        elif duo in MULTI2:
            append(("sym", duo, line, doc))
            i += 2
        else:
            append(("sym", c, line, doc))
            i += 1
        doc = None
    return toks


def ann_name_lite(a: str) -> str:
    return a.split("(", 1)[0]


def kdoc_summary(raw: str | None) -> str:
    if not raw:
        return ""
    body = re.sub(r"^/\*\*|\*/$", "", raw.strip())
    lines = [re.sub(r"^\s*\*\s?", "", ln).strip() for ln in body.splitlines()]
    text = []
    for ln in lines:
        if ln.startswith("@"):
            break
        if ln:
            text.append(ln)
        elif text:
            break
    s = " ".join(text)
    s = re.sub(r"\[([^\]]+)\]", r"\1", s)
    s = re.sub(r"\{@\w+\s+([^}]*)\}", r"\1", s)
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    s = m.group(1) if m else s
    return s[:160]


def ttext(toks) -> str:
    out: list[str] = []
    pk = ps = None
    for k, s, _, _ in toks:
        if k == "str":
            s = '"' + s + '"'
        elif k == "chr":
            s = "'c'"
        if pk is not None:
            if pk in ("id", "num", "str", "chr") and k in ("id", "num", "str", "chr"):
                out.append(" ")
            elif ps in (",", ":") or s == "->" or ps == "->" or s == "=" or ps == "=":
                out.append(" ")
            elif ps == "?" and k == "id":
                out.append(" ")
        out.append(s)
        pk, ps = k, s
    return "".join(out)


def dotted_refs(toks, exclude=()) -> list[str]:
    """Nomes de tipos (possivelmente qualificados) que aparecem em uma lista de tokens."""
    res: list[str] = []
    i, n = 0, len(toks)
    while i < n:
        if toks[i][0] == "id":
            parts = [toks[i][1]]
            j = i + 1
            while j + 1 < n and toks[j][1] == "." and toks[j][0] == "sym" and toks[j + 1][0] == "id":
                parts.append(toks[j + 1][1])
                j += 2
            if any(p[:1].isupper() for p in parts):
                nm = ".".join(parts)
                if len(parts[-1]) > 1 and parts[-1] not in exclude and nm not in exclude and not (len(parts) == 1 and parts[0] in KEYWORDS):
                    res.append(nm)
            i = j
        else:
            i += 1
    return res


class FlowNode(TypedDict):
    id: int
    kind: str   # "entry" | "if" | "when" | "when_arm" | "return" | "throw" | "exit" |
                # "while" | "do_while" | "for" | "break" | "continue" |
                # "try" | "catch" | "finally" | "suspend" | "nullcheck"
    line: int
    label: str


class FlowEdge(TypedDict):
    src: int
    dst: int
    label: str  # "true" | "false" | "arm" | "next"


class FlowGraph(TypedDict):
    nodes: list[FlowNode]
    edges: list[FlowEdge]


# [name, type, annots] -- lista posicional (formato compacto no JSONL), nao TypedDict: cada
# campo e lido por indice/desestruturacao (ex.: "for pn, pt, *rest in s['params']"), nunca por
# chave, entao um TypedDict daria uma falsa impressao de acesso por nome.
ParamInfo = list[Any]

MAX_FLOW_NODES = 200  # protecao contra funcao patologica (gerada, minificada, etc.)


class _FlowBuilder:
    """Constroi um grafo de fluxo de execucao (if/when, incluindo os "early returns" que um
    contador de complexidade nao distingue) reaproveitando os mesmos primitivos que o resto do
    parser ja usa pra achar blocos e fim de instrucao — nao e um AST/CFG de compilador, e uma
    descida recursiva sobre o MESMO stream de tokens, no nivel de instrucao (nao de expressao).
    Usada so internamente por Parser.flow_graph(); mantem o estado da recursao (contador de id,
    nos, arestas) fora do Parser pra nao poluir o estado dele."""

    def __init__(self, parser: "Parser"):
        self.p = parser
        self.T = parser.T
        self.nodes: list[FlowNode] = []
        self.edges: list[FlowEdge] = []
        self.next_id = 0
        self.capped = False
        self.loop_stack: list[int] = []          # id do no do loop mais proximo (p/ continue)
        self.pending_breaks: list[list[tuple[int, str]]] = []  # saidas de 'break' por nivel de loop

    def _node(self, kind: str, line: int, label: str = "") -> int:
        nid = self.next_id
        self.next_id += 1
        self.nodes.append({"id": nid, "kind": kind, "line": line, "label": label[:60]})
        return nid

    def _edge(self, src: int | None, dst: int | None, label: str) -> None:
        if src is not None and dst is not None:
            self.edges.append({"src": src, "dst": dst, "label": label})

    def build(self, a: int, b: int) -> FlowGraph | None:
        if a >= b:
            return None
        entry = self._node("entry", self.T[a][2])
        exits = self._block(a, b, [(entry, "next")])
        # so entry/return/throw ate aqui -> reta sem ramo/loop/try, nao vale grafo (ex.: funcao
        # de uma linha so). Um unico no de loop ja conta como interessante por causa do
        # back-edge, mesmo sem nenhum if/when dentro.
        if not any(n["kind"] not in ("entry", "return", "throw") for n in self.nodes):
            return None
        exitn = self._node("exit", self.T[b - 1][2])
        for src, lbl in exits:
            self._edge(src, exitn, lbl)
        return {"nodes": self.nodes, "edges": self.edges}

    def _skip_stmt(self, j: int, b: int) -> int:
        e = self.p.scan_expr_end(j, b)
        if e < b and self.T[e][0] == "sym" and self.T[e][1] == ";":
            e += 1
        return max(e, j + 1)

    def _body_range(self, k: int, b: int) -> tuple[int, int]:
        """Intervalo [inicio, fim) de um corpo de bloco: com chaves (fim = INDICE da chave que
        fecha, quem chama precisa +1 pra continuar depois dela) ou uma unica instrucao (fim ja
        aponta pra depois dela)."""
        if k < b and self.T[k][0] == "sym" and self.T[k][1] == "{":
            close = self.p.match_pair(k)
            return k + 1, close
        e = self._skip_stmt(k, b)
        return k, e

    def _else_boundary(self, j: int, b: int) -> int:
        """Posicao do 'else' no mesmo nivel (profundidade 0), se houver antes de b — usado so
        pra limitar o 'then' de um if sem chaves ('if (x) foo() else bar()'), porque
        scan_expr_end nao sabe que 'else' fecha o ramo anterior."""
        T = self.T
        depth = 0
        for e in range(j, b):
            kk, ss = T[e][0], T[e][1]
            if kk == "sym" and ss in OPEN:
                depth += 1
            elif kk == "sym" and ss in CLOSE:
                depth -= 1
            elif depth == 0 and kk == "id" and ss == "else":
                return e
        return b

    def _find_assign_eq(self, j: int, b: int) -> int | None:
        """Acha o '=' de 'val/var nome [: Tipo] = ...' comecando em j (token 'val'/'var'),
        limitado a uma janela curta — o bastante pra declaracao, nao pra corpo inteiro."""
        T = self.T
        depth = 0
        for e in range(j + 1, min(b, j + 40)):
            kk, ss = T[e][0], T[e][1]
            if kk == "sym" and ss in OPEN:
                depth += 1
            elif kk == "sym" and ss in CLOSE:
                if depth == 0:
                    return None
                depth -= 1
            elif depth == 0 and kk == "sym" and ss == "=":
                return e
            elif depth == 0 and kk == "sym" and ss == ";":
                return None
        return None

    def _branch_stmt(self, j: int, b: int, cur: list[tuple[int, str]],
                      terminal: bool) -> tuple[int, list[tuple[int, str]]] | None:
        """Se o token em j e 'if'/'when', desce a recursao; se 'terminal', cada saida do
        if/when vira um no terminal (usado quando o if/when e o VALOR de um return/throw —
        'return when { ... }' e um padrao Kotlin idiomatico, cada ramo dele e um return
        implicito). None se j nao e se nem when (chamador segue o fluxo normal)."""
        k, s = self.T[j][0], self.T[j][1]
        if not (k == "id" and s in ("if", "when")):
            return None
        end, exits = (self._if if s == "if" else self._when)(j, b, cur)
        if not terminal:
            return end, exits
        term_kind = "return"
        for src, lbl in exits:
            node = self._node(term_kind, self.T[j][2], "")
            self._edge(src, node, lbl)
        return end, []

    def _block(self, a: int, b: int, preds: list[tuple[int, str]]) -> list[tuple[int, str]]:
        j, cur = a, preds
        while j < b and not self.capped:
            if self.next_id > MAX_FLOW_NODES:
                self.capped = True
                break
            k, s = self.T[j][0], self.T[j][1]
            if k == "id" and s in ("if", "when"):
                j, cur = self._branch_stmt(j, b, cur, terminal=False)
                continue
            if k == "id" and s == "while":
                j, cur = self._while(j, b, cur)
                continue
            if k == "id" and s == "do":
                j, cur = self._do_while(j, b, cur)
                continue
            if k == "id" and s == "for":
                j, cur = self._for(j, b, cur)
                continue
            if k == "id" and s == "try":
                j, cur = self._try(j, b, cur)
                continue
            if k == "id" and s == "continue" and self.loop_stack:
                node = self._node("continue", self.T[j][2], "")
                for src, lbl in cur:
                    self._edge(src, node, lbl)
                self._edge(node, self.loop_stack[-1], "continue")
                cur = []
                j = self._skip_stmt(j, b)
                continue
            if k == "id" and s == "break" and self.pending_breaks:
                node = self._node("break", self.T[j][2], "")
                for src, lbl in cur:
                    self._edge(src, node, lbl)
                self.pending_breaks[-1].append((node, "break"))
                cur = []
                j = self._skip_stmt(j, b)
                continue
            if k == "id" and s in ("return", "throw"):
                nxt = self.T[j + 1] if j + 1 < b else None
                if nxt and nxt[0] == "id" and nxt[1] in ("if", "when"):
                    j, cur = self._branch_stmt(j + 1, b, cur, terminal=True)
                    continue
                end = self._skip_stmt(j, b)
                marker = self._lexical_marker(j + 1, end)  # ex.: 'return withContext(...) { ... }'
                if marker is not None:
                    for src, lbl in cur:
                        self._edge(src, marker, lbl)
                    cur = [(marker, "next")]
                node = self._node(s, self.T[j][2], ttext(self.T[j:min(j + 6, b)]))
                for src, lbl in cur:
                    self._edge(src, node, lbl)
                cur = []
                j = end
                continue
            if k == "id" and s in ("val", "var"):
                eq = self._find_assign_eq(j, b)
                if eq is not None:
                    branch = self._branch_stmt(eq + 1, b, cur, terminal=False)
                    if branch:
                        j, cur = branch
                        continue
            end = self._skip_stmt(j, b)
            marker = self._lexical_marker(j, end)
            if marker is not None:
                for src, lbl in cur:
                    self._edge(src, marker, lbl)
                cur = [(marker, "next")]
            j = end
        return cur

    def _lexical_marker(self, a: int, e: int) -> int | None:
        """Um no pass-through por instrucao no maximo: tenta suspensao primeiro, senao
        nullability. Statements com os dois sinais (raro) so registram o primeiro achado —
        mesma pegada leve do resto do arquivo, nao vale complicar pra um caso raro."""
        return self._suspend_marker(a, e) or self._nullcheck_marker(a, e)

    def _suspend_marker(self, a: int, e: int) -> int | None:
        """Deteccao lexica (sem resolucao de tipo, mesmo espirito do 'coroutine_ops' da Parte 1
        de coroutines): instrucao chama um coroutine builder ou '.await(' -> vira um no
        'suspend' *pass-through* inline (nao e ramo, so marca ONDE dentro do fluxo a suspensao
        acontece — 'coroutine_ops' na Parte 1 so dizia QUE a funcao suspende, nao onde)."""
        T = self.T
        for i in range(a, e):
            kk, ss = T[i][0], T[i][1]
            if kk != "id":
                continue
            if ss in COROUTINE_BUILDERS:
                nxt = T[i + 1] if i + 1 < e else None
                if nxt and nxt[0] == "sym" and nxt[1] in ("(", "{"):
                    return self._node("suspend", T[i][2], ss)
            elif ss == "await":
                prev = T[i - 1] if i > a else None
                nxt = T[i + 1] if i + 1 < e else None
                if prev and prev[0] == "sym" and prev[1] == "." and nxt and nxt[0] == "sym" and nxt[1] == "(":
                    return self._node("suspend", T[i][2], "await")
        return None

    def _nullcheck_marker(self, a: int, e: int) -> int | None:
        """Deteccao lexica de safe-call ('?.') ou elvis ('?:') dentro da instrucao — mesmo
        espirito pass-through do marcador de suspensao: nao tenta modelar os dois caminhos da
        nulidade como ramos true/false separados (isso exigiria um scanner de expressao a
        parte, escopo maior), so marca ONDE dentro do fluxo existe um ponto de decisao por
        nulidade."""
        T = self.T
        for i in range(a, e):
            if T[i][0] == "sym" and T[i][1] in ("?.", "?:"):
                return self._node("nullcheck", T[i][2], T[i][1])
        return None

    def _if(self, j: int, b: int, preds: list[tuple[int, str]]) -> tuple[int, list[tuple[int, str]]]:
        T = self.T
        ln = T[j][2]
        k = j + 1
        cond = ""
        if k < b and T[k][0] == "sym" and T[k][1] == "(":
            close = self.p.match_pair(k)
            cond = ttext(T[k + 1:close])
            k = close + 1
        node = self._node("if", ln, cond)
        for src, lbl in preds:
            self._edge(src, node, lbl)
        if k < b and T[k][0] == "sym" and T[k][1] == "{":
            close = self.p.match_pair(k)
            then_a, then_b, after_then = k + 1, close, close + 1
        else:
            then_a = k
            after_then = self._then_end(k, b)
            then_b = after_then
        then_exits = self._block(then_a, then_b, [(node, "true")])
        k = after_then
        if k < b and T[k][0] == "id" and T[k][1] == "else":
            k += 1
            if k < b and T[k][0] == "sym" and T[k][1] == "{":
                close = self.p.match_pair(k)
                else_a, else_b, after_else = k + 1, close, close + 1
            else:
                else_a = k
                after_else = self._skip_stmt(k, b)
                else_b = after_else
            else_exits = self._block(else_a, else_b, [(node, "false")])
            return after_else, then_exits + else_exits
        return k, then_exits + [(node, "false")]

    def _then_end(self, k: int, b: int) -> int:
        """Como scan_expr_end, mas tambem para antes de um 'else' no mesmo nivel — necessario
        pra 'if (x) foo() else bar()' sem chaves, onde scan_expr_end sozinho nao sabe que
        'else' fecha o ramo anterior (ele so entende quebra de linha/profundidade de parenteses)."""
        limit = self._else_boundary(k, b)
        e = self.p.scan_expr_end(k, limit)
        if e < limit and self.T[e][0] == "sym" and self.T[e][1] == ";":
            e += 1
        return max(e, k + 1)

    def _loop_body_range(self, k: int, b: int) -> tuple[int, int, int]:
        """(inicio, fim, posicao-apos) do corpo de um loop — igual ao padrao ja usado em
        _if para nao repetir o bug de off-by-one entre indice da chave de fechamento e
        posicao de continuacao (ver _then_end/_else_boundary)."""
        if k < b and self.T[k][0] == "sym" and self.T[k][1] == "{":
            close = self.p.match_pair(k)
            return k + 1, close, close + 1
        after = self._skip_stmt(k, b)
        return k, after, after

    def _while(self, j: int, b: int, preds: list[tuple[int, str]]) -> tuple[int, list[tuple[int, str]]]:
        T = self.T
        ln = T[j][2]
        k = j + 1
        cond = ""
        if k < b and T[k][0] == "sym" and T[k][1] == "(":
            close = self.p.match_pair(k)
            cond = ttext(T[k + 1:close])
            k = close + 1
        node = self._node("while", ln, cond)
        for src, lbl in preds:
            self._edge(src, node, lbl)
        body_a, body_b, after = self._loop_body_range(k, b)
        self.loop_stack.append(node)
        self.pending_breaks.append([])
        body_exits = self._block(body_a, body_b, [(node, "true")])
        for src, lbl in body_exits:
            self._edge(src, node, "next")  # back-edge: fim do corpo reavalia a condicao
        breaks = self.pending_breaks.pop()
        self.loop_stack.pop()
        return after, breaks + [(node, "false")]

    def _do_while(self, j: int, b: int, preds: list[tuple[int, str]]) -> tuple[int, list[tuple[int, str]]]:
        T = self.T
        ln = T[j][2]
        body_a, body_b, after_body = self._loop_body_range(j + 1, b)
        node = self._node("do_while", ln, "")
        for src, lbl in preds:
            self._edge(src, node, "next")
        self.loop_stack.append(node)
        self.pending_breaks.append([])
        body_exits = self._block(body_a, body_b, [(node, "next")])
        for src, lbl in body_exits:
            self._edge(src, node, "next")  # back-edge: fim do corpo reavalia a condicao
        breaks = self.pending_breaks.pop()
        self.loop_stack.pop()
        k, cond, after = after_body, "", after_body
        if k < b and T[k][0] == "id" and T[k][1] == "while":
            k += 1
            if k < b and T[k][0] == "sym" and T[k][1] == "(":
                close = self.p.match_pair(k)
                cond = ttext(T[k + 1:close])
                k = close + 1
            if k < b and T[k][0] == "sym" and T[k][1] == ";":
                k += 1
            after = k
        self.nodes[node]["label"] = cond[:60]
        return after, breaks + [(node, "false")]

    def _for(self, j: int, b: int, preds: list[tuple[int, str]]) -> tuple[int, list[tuple[int, str]]]:
        T = self.T
        ln = T[j][2]
        k = j + 1
        clause = ""
        if k < b and T[k][0] == "sym" and T[k][1] == "(":
            close = self.p.match_pair(k)
            clause = ttext(T[k + 1:close])
            k = close + 1
        node = self._node("for", ln, clause)
        for src, lbl in preds:
            self._edge(src, node, lbl)
        body_a, body_b, after = self._loop_body_range(k, b)
        self.loop_stack.append(node)
        self.pending_breaks.append([])
        body_exits = self._block(body_a, body_b, [(node, "true")])
        for src, lbl in body_exits:
            self._edge(src, node, "next")  # back-edge: proxima iteracao
        breaks = self.pending_breaks.pop()
        self.loop_stack.pop()
        return after, breaks + [(node, "false")]

    def _try(self, j: int, b: int, preds: list[tuple[int, str]]) -> tuple[int, list[tuple[int, str]]]:
        """Simplificacao deliberada: a aresta try->catch e uma aproximacao ("uma excecao em
        algum ponto do try pode cair aqui"), nao um site exato — rastrear de onde exatamente
        dentro do try cada excecao pode vir exigiria acompanhar 'ha um catch pendente' por toda
        a recursao de _block (se/quando/loop aninhados inclusive), custo alto pra ganho marginal
        (mesmo espirito de aproximacao ja usado no campo 'conf' de aresta em outras partes do
        arquivo). Pelo mesmo motivo, um return/throw de dentro do try/catch NAO e redirecionado
        atraves do finally aqui: ele já vira um no terminal normal (ver _block), so nao passa
        pelo no 'finally' antes de terminar."""
        T = self.T
        ln = T[j][2]
        k = j + 1
        if k < b and T[k][0] == "sym" and T[k][1] == "(":
            # try-with-resources (Java): 'try (Resource r = ...) { ... }' -- so pula, o
            # recurso em si nao vira no (mesma pegada leve do resto do grafo).
            k = self.p.match_pair(k) + 1
        node = self._node("try", ln, "")
        for src, lbl in preds:
            self._edge(src, node, lbl)
        if not (k < b and T[k][0] == "sym" and T[k][1] == "{"):
            return self._skip_stmt(j, b), preds
        close = self.p.match_pair(k)
        exits = self._block(k + 1, close, [(node, "next")])
        k = close + 1
        while k < b and T[k][0] == "id" and T[k][1] == "catch":
            k += 1
            ctype = ""
            if k < b and T[k][0] == "sym" and T[k][1] == "(":
                cclose = self.p.match_pair(k)
                ctype = ttext(T[k + 1:cclose])
                k = cclose + 1
            cnode = self._node("catch", T[k][2] if k < b else ln, ctype)
            self._edge(node, cnode, "catch")
            if k < b and T[k][0] == "sym" and T[k][1] == "{":
                cbclose = self.p.match_pair(k)
                exits.extend(self._block(k + 1, cbclose, [(cnode, "next")]))
                k = cbclose + 1
            else:
                exits.append((cnode, "next"))
        if k < b and T[k][0] == "id" and T[k][1] == "finally":
            k += 1
            if k < b and T[k][0] == "sym" and T[k][1] == "{":
                fclose = self.p.match_pair(k)
                fnode = self._node("finally", T[k][2], "")
                for src, lbl in exits:
                    self._edge(src, fnode, lbl)
                exits = self._block(k + 1, fclose, [(fnode, "next")])
                k = fclose + 1
        return k, exits

    def _when(self, j: int, b: int, preds: list[tuple[int, str]]) -> tuple[int, list[tuple[int, str]]]:
        T = self.p.T
        ln = T[j][2]
        m = j + 1
        subject = ""
        if m < b and T[m][0] == "sym" and T[m][1] == "(":
            close = self.p.match_pair(m)
            subject = ttext(T[m + 1:close])
            m = close + 1
        if not (m < b and T[m][0] == "sym" and T[m][1] == "{"):
            return self._skip_stmt(j, b), preds
        wclose = self.p.match_pair(m)
        node = self._node("when", ln, subject)
        for src, lbl in preds:
            self._edge(src, node, lbl)
        exits: list[tuple[int, str]] = []
        k, depth, arm_start = m + 1, 0, m + 1
        while k < wclose and not self.capped:
            kk, ss = T[k][0], T[k][1]
            if kk == "sym" and ss in OPEN:
                depth += 1
            elif kk == "sym" and ss in CLOSE:
                depth -= 1
            elif kk == "sym" and ss == "->" and depth == 0:
                cond_txt = ttext(T[arm_start:k])
                arm_node = self._node("when_arm", T[k][2], cond_txt)
                self._edge(node, arm_node, "arm")
                if k + 1 < wclose and T[k + 1][0] == "sym" and T[k + 1][1] == "{":
                    close = self.p.match_pair(k + 1)
                    body_a, body_b = k + 2, close
                    after_body = close + 1
                else:
                    body_a = k + 1
                    after_body = self._arm_body_end(body_a, wclose)
                    body_b = after_body
                exits.extend(self._block(body_a, body_b, [(arm_node, "next")]))
                k = arm_start = after_body
                continue
            k += 1
        return wclose + 1, exits

    def _arm_body_end(self, k: int, b: int) -> int:
        """Fim do corpo (sem chaves) de um braco de when: como scan_expr_end, mas tambem para
        antes de um 'else' que na verdade introduz o PROXIMO braco ('else -> ...') — sem isso,
        scan_expr_end trata 'else' depois de quebra de linha como continuacao de if/else (regra
        valida fora de when) e engole o braco catch-all inteiro dentro do corpo do braco anterior."""
        T = self.T
        limit = b
        depth = 0
        for e in range(k, b):
            kk, ss = T[e][0], T[e][1]
            if kk == "sym" and ss in OPEN:
                depth += 1
            elif kk == "sym" and ss in CLOSE:
                if depth == 0:
                    limit = e
                    break
                depth -= 1
            elif depth == 0 and kk == "id" and ss == "else":
                nxt = T[e + 1] if e + 1 < b else None
                if nxt and nxt[0] == "sym" and nxt[1] == "->":
                    limit = e
                    break
        e = self.p.scan_expr_end(k, limit)
        if e < limit and T[e][0] == "sym" and T[e][1] == ";":
            e += 1
        return max(e, k + 1)


# =========================================================================== #
# Parser base + Kotlin
# =========================================================================== #
class Parser:
    def __init__(self, src: str, rel: str):
        self.src, self.rel = src, rel
        self.T = lex(src)
        self.syms: list[dict] = []
        self.package = ""
        self.imports: list[list] = []

    # ---- utilidades de tokens ----
    def match_pair(self, i: int) -> int:
        T = self.T
        o = T[i][1]
        c = OPEN[o]
        d = 0
        for j in range(i, len(T)):
            k, s = T[j][0], T[j][1]
            if k == "sym":
                if s == o:
                    d += 1
                elif s == c:
                    d -= 1
                    if d == 0:
                        return j
        return len(T) - 1

    def match_pair_back(self, i: int):
        """Indice do abre-parenteses/chave/colchete que fecha em T[i] (None se nao achar)."""
        T = self.T
        c = T[i][1]
        o = CLOSE_OPEN.get(c)
        if o is None:
            return None
        d = 0
        for j in range(i, -1, -1):
            k, s = T[j][0], T[j][1]
            if k == "sym":
                if s == c:
                    d += 1
                elif s == o:
                    d -= 1
                    if d == 0:
                        return j
        return None

    def _is_chained_catch(self, name_idx: int) -> bool:
        """'catch' e keyword (try/catch), mas tambem e o operador Flow/Reactor '.catch { }' —
        so distingue por contexto: precedido de '.'/'?.' e uma chamada de verdade, nao uma
        clausula catch(Tipo). Usado tanto em extract_refs (pra nao perder o operador na lista
        de calls) quanto na resolucao de cadeia (_chain_recv/_chain_recv_paren)."""
        T = self.T
        return (name_idx - 1 >= 0 and T[name_idx - 1][0] == "sym" and T[name_idx - 1][1] in (".", "?."))

    def _chain_recv(self, i: int) -> str:
        """Recv para acesso encadeado (obj.foo().bar(), foo().bar(), builder { }.step()): se o
        token antes do ponto fecha uma chamada (parenteses ou o lambda trailing de uma
        chamada), codifica '@call:<qualificador>.<nome>' no mesmo formato usado para variaveis
        locais (ver _local_decl / Graph.resolve_call) em vez de desistir com '?', permitindo
        resolver o retorno da chamada anterior. Deliberadamente NAO tenta isso para blocos de
        controle (if/when/try/...) nem corpos de classe/object/interface usados como
        expressao — ambiguo demais para essa heuristica; cai em '?' como antes."""
        if i < 0:
            return "?"
        T = self.T
        k, s = T[i][0], T[i][1]
        if k == "id":
            return s
        if k == "sym" and s == ")":
            return self._chain_recv_paren(i)
        if k == "sym" and s == "}":
            o = self.match_pair_back(i)
            if o is None or o - 1 < 0:
                return "?"
            prev = T[o - 1]
            if prev[0] == "sym" and prev[1] == ")":
                return self._chain_recv_paren(o - 1)
            if (prev[0] == "id" and (prev[1] not in KEYWORDS or (prev[1] == "catch" and self._is_chained_catch(o - 1)))
                    and not (o - 2 >= 0 and T[o - 2][1] in ("class", "object", "interface", ":"))):
                return self._chain_call_name(o - 1, prev[1])
        return "?"

    def _chain_recv_paren(self, i: int) -> str:
        """Mesma logica de _chain_recv para o caso 'fecha em )': acha o nome da chamada cujo
        fechamento de parenteses e o token em i."""
        T = self.T
        o = self.match_pair_back(i)
        if o is None or o - 1 < 0 or T[o - 1][0] != "id":
            return "?"
        if T[o - 1][1] in KEYWORDS and not (T[o - 1][1] == "catch" and self._is_chained_catch(o - 1)):
            return "?"
        return self._chain_call_name(o - 1, T[o - 1][1])

    def _chain_call_name(self, name_idx: int, name: str) -> str:
        T = self.T
        if (name_idx - 2 >= 0 and T[name_idx - 1][0] == "sym" and T[name_idx - 1][1] in (".", "?.")
                and T[name_idx - 2][0] == "id"):
            return f"@call:{T[name_idx - 2][1]}.{name}"
        return f"@call:.{name}"

    def match_angle(self, i: int) -> int:
        T = self.T
        d = 0
        for j in range(i, min(len(T), i + 400)):
            if T[j][0] == "sym":
                if T[j][1] == "<":
                    d += 1
                elif T[j][1] == ">":
                    d -= 1
                    if d == 0:
                        return j
                elif T[j][1] in (";", "{", "}", "="):
                    break
        return i

    def parse_tparams(self, i: int):
        T = self.T
        c = self.match_angle(i)
        names, expect = set(), True
        depth = 0
        for j in range(i + 1, c):
            k, s = T[j][0], T[j][1]
            if k == "sym":
                if s in ("<", "("):
                    depth += 1
                elif s in (">", ")"):
                    depth -= 1
                elif s == "," and depth == 0:
                    expect = True
            elif k == "id" and expect and depth == 0 and s not in ("in", "out", "reified"):
                names.add(s)
                expect = False
        return names, c + 1

    def find_comma(self, a: int, close: int) -> int:
        T = self.T
        depth = angle = 0
        dflt = False
        for j in range(a, close):
            if T[j][0] != "sym":
                continue
            s = T[j][1]
            if s in OPEN:
                depth += 1
            elif s in CLOSE:
                depth -= 1
            elif s == "<" and not dflt:
                angle += 1
            elif s == ">" and not dflt and angle > 0:
                angle -= 1
            elif s == "=" and depth == 0 and angle == 0:
                dflt = True
            elif s == "," and depth == 0 and angle == 0:
                return j
        return close

    def scan_type(self, i: int, end: int, stops) -> int:
        T = self.T
        depth = 0
        prev = None
        j = i
        while j < end:
            k, s, ln, _ = T[j]
            if k == "sym":
                if s in ("(", "[", "<"):
                    depth += 1
                elif s in (")", "]", ">"):
                    if depth == 0:
                        return j
                    depth -= 1
            if depth == 0 and k == "sym" and s == ";":
                return j
            if depth == 0 and s in stops and k in ("sym", "id"):
                return j
            if depth == 0 and prev is not None and ln > prev[2] and prev[1] not in TYPE_CONT_PREV and s not in TYPE_CONT_NEXT:
                return j
            prev = T[j]
            j += 1
        return end

    def scan_expr_end(self, i: int, limit: int) -> int:
        T = self.T
        depth = 0
        prev = None
        j = i
        while j < limit:
            k, s, ln, _ = T[j]
            if k == "sym":
                if s in OPEN:
                    depth += 1
                elif s in CLOSE:
                    if depth == 0:
                        return j
                    depth -= 1
                elif depth == 0 and s == ";":
                    return j
            if depth == 0 and prev is not None and ln > prev[2]:
                cont = (prev[0] == "sym" and prev[1] in CONT_PREV) or (prev[0] == "id" and prev[1] in CONT_PREV_ID)
                cont = cont or (s in CONT_NEXT and k in ("sym", "id"))
                if not cont:
                    return j
            prev = T[j]
            j += 1
        return limit

    def parse_annot(self, i: int, end: int):
        T = self.T
        j = i + 1
        if j >= end:
            return end, ""
        if T[j][0] == "sym" and T[j][1] == "[":
            return self.match_pair(j) + 1, ""
        site = ""
        if T[j][1] in USE_SITES and j + 1 < end and T[j + 1][1] == ":":
            site = T[j][1]
            j += 2
        parts: list[str] = []
        while j < end and T[j][0] == "id":
            parts.append(T[j][1])
            if j + 2 < end and T[j + 1][1] == "." and T[j + 2][0] == "id":
                j += 2
                continue
            j += 1
            break
        args = ""
        if j < end and T[j][0] == "sym" and T[j][1] == "(" and T[j][2] == T[j - 1][2]:
            c = self.match_pair(j)
            args = ttext(T[j + 1:c])
            j = c + 1
        if site == "file" or not parts:
            return j, ""
        return j, parts[-1] + (f"({args[:160]})" if args else "")

    def new_sym(self, **kw) -> int:
        d = {"kind": "", "name": "", "line": 0, "end": 0, "vis": "public", "mods": [], "annots": [], "doc": "",
             "owner": -1, "sig": "", "supers": [], "super_calls": [], "recv": "", "ret": "", "cc": 0,
             "params": [], "calls": [], "types": [], "locals": {}, "routes": [], "inject": [], "ptype": "",
             "tparams": [], "strs": [], "fields": [], "throws": [], "catches": [], "fp": "", "ntok": 0}
        d.update(kw)
        vis = "public"
        for m in d["mods"]:
            if m in ("private", "protected", "internal"):
                vis = m
        d["vis"] = vis
        self.syms.append(d)
        return len(self.syms) - 1

    # ---- referencias e complexidade ----
    def fingerprint(self, a: int, b: int) -> tuple:
        """Assinatura estrutural do corpo: identificadores viram marcador, literais tambem."""
        out = []
        for k, txt, _, _ in self.T[a:b]:
            if k == "id":
                out.append(txt if txt in KEYWORDS else "#")
            elif k in ("str", "num", "chr"):
                out.append("$")
            else:
                out.append(txt)
        if len(out) < 24:
            return "", len(out)
        return hashlib.sha1(" ".join(out).encode()).hexdigest()[:16], len(out)

    def extract_refs(self, a: int, b: int, tp, sym: dict) -> None:
        T = self.T
        calls, types, locs, routes = sym["calls"], set(sym["types"]), sym["locals"], sym["routes"]
        fields, throws, catches = sym["fields"], sym["throws"], sym["catches"]
        rstack: list[tuple[str, int]] = []
        lambda_stack: list[tuple[int, int]] = []
        strs = sym["strs"]
        j = a
        while j < b:
            k, s, ln, _ = T[j]
            if k != "id":
                if k == "str" and len(s) > 3 and len(strs) < 60:
                    strs.append([s[:300], ln])
                if k == "str" and "${" in s and len(calls) < 400:
                    for m in _INTERP_CALL.finditer(s):
                        chain = m.group(1).replace("?.", ".").split(".")
                        calls.append([chain[-1], chain[-2] if len(chain) > 1 else "", ln])
                j += 1
                continue
            while rstack and j > rstack[-1][1]:
                rstack.pop()
            while lambda_stack and j > lambda_stack[-1][1]:
                lambda_stack.pop()
            if s in KEYWORDS and not (s == "catch" and self._is_chained_catch(j)):
                if s in ("val", "var"):
                    self._local_decl(j, b, locs)
                elif s in ("throw", "new") and j + 1 < b and T[j + 1][0] == "id" and T[j + 1][1][:1].isupper():
                    if s == "throw":
                        throws.append([T[j + 1][1], ln])
                elif s == "catch" and j + 1 < b and T[j + 1][1] == "(":
                    for m2 in range(j + 2, min(b, j + 12)):
                        if T[m2][0] == "id" and T[m2][1][:1].isupper():
                            catches.append([T[m2][1], ln])
                            break
                j += 1
                continue
            prev = T[j - 1] if j > a else None
            nxt = T[j + 1] if j + 1 < b else None
            pdot = prev is not None and prev[0] == "sym" and prev[1] in (".", "?.")
            pref = prev is not None and prev[0] == "sym" and prev[1] == "::"
            up = s[:1].isupper()
            is_call, ta_end = False, None
            if nxt is not None and nxt[0] == "sym":
                if nxt[1] == "(":
                    is_call = True
                elif nxt[1] == "{" and not up and not (prev and prev[1] in ("class", "object", "interface")):
                    is_call = True
                elif nxt[1] == "<":
                    ta_end = self._type_args_end(j + 1, b)
                    if ta_end is not None and ta_end + 1 < b and T[ta_end + 1][1] == "(":
                        is_call = True
                        types.update(dotted_refs(T[j + 2:ta_end], tp))
            if is_call:
                bare = not (pdot or pref)
                recv = ""
                if pdot or pref:
                    recv = self._chain_recv(j - 2 if j - 2 >= a else -1)
                elif lambda_stack:
                    recv = f"@lambda:{lambda_stack[-1][0]}"
                calls.append([s, recv, ln])
                if nxt[1] == "{":
                    lambda_stack.append((len(calls) - 1, self.match_pair(j + 1)))
                elif nxt[1] == "(":
                    c = self.match_pair(j + 1)
                    if c + 1 < b and T[c + 1][1] == "{":
                        lambda_stack.append((len(calls) - 1, self.match_pair(c + 1)))
                if s in HTTP_VERBS and bare and nxt and nxt[1] == "(" and j + 2 < b and T[j + 2][0] == "str":
                    pre = "".join(p for p, _ in rstack)
                    routes.append([HTTP_VERBS[s], (pre + T[j + 2][1]) or "/", ln])
                elif s == "route" and bare and nxt and nxt[1] == "(" and j + 2 < b and T[j + 2][0] == "str":
                    c = self.match_pair(j + 1)
                    if c + 1 < b and T[c + 1][1] == "{":
                        rstack.append((T[j + 2][1], self.match_pair(c + 1)))
            elif pref and not up:
                r = T[j - 2] if j - 2 >= a else None
                calls.append([s, r[1] if r is not None and r[0] == "id" else "", ln])
            elif pdot and not up and len(fields) < 120:
                recv = self._chain_recv(j - 2 if j - 2 >= a else -1)
                nx = T[j + 1] if j + 1 < b else None
                mode = "w" if (nx is not None and nx[0] == "sym" and nx[1] in ("=", "+=", "-=", "*=", "/=", "%=")) else "r"
                fields.append([s, recv, ln, mode])
            elif up and not (pdot and s.isupper()) and s not in tp and len(s) > 1:
                types.add(s)
            j += 1
        sym["types"] = sorted(types)

    def _type_args_end(self, i: int, b: int):
        T = self.T
        d = 0
        for j in range(i, min(b, i + 60)):
            k, s = T[j][0], T[j][1]
            if k == "sym":
                if s == "<":
                    d += 1
                elif s == ">":
                    d -= 1
                    if d == 0:
                        return j
                elif s not in (",", "?", ".", "*", "->", "(", ")", "[", "]", ":"):
                    return None
            elif k not in ("id",):
                return None
        return None

    def _local_decl(self, j: int, b: int, locs: dict) -> None:
        T = self.T
        if j + 2 >= b or T[j + 1][0] != "id":
            return
        name = T[j + 1][1]
        t2 = T[j + 2]
        if t2[1] == ":" and t2[0] == "sym":
            for m in range(j + 3, min(b, j + 12)):
                if T[m][0] == "id" and T[m][1][:1].isupper():
                    locs[name] = T[m][1]
                    return
                if T[m][0] == "sym" and T[m][1] in ("=", ";"):
                    return
        elif t2[1] == "=" and j + 4 < b and T[j + 3][0] == "id":
            if T[j + 3][1][:1].isupper() and T[j + 4][1] in ("(", "."):
                locs[name] = T[j + 3][1]
            elif T[j + 4][1] in (".", "?.") and j + 6 < b and T[j + 5][0] == "id" and T[j + 6][1] == "(":
                locs[name] = f"@call:{T[j + 3][1]}.{T[j + 5][1]}"
            elif T[j + 4][1] == "(":
                locs[name] = f"@call:.{T[j + 3][1]}"

    def complexity(self, a: int, b: int) -> int:
        T = self.T
        cc, stack, wb = 1, [], set()
        for j in range(a, b):
            k, s = T[j][0], T[j][1]
            if k == "id":
                if s in ("if", "for", "while", "catch"):
                    cc += 1
                elif s == "when":
                    m = j + 1
                    if m < b and T[m][1] == "(" and T[m][0] == "sym":
                        m = self.match_pair(m) + 1
                    if m < b and T[m][1] == "{":
                        wb.add(m)
            elif k == "sym":
                if s in ("&&", "||", "?:"):
                    cc += 1
                elif s == "{":
                    stack.append(j in wb)
                elif s == "}":
                    if stack:
                        stack.pop()
                elif s == "->" and stack and stack[-1]:
                    cc += 1
        return cc

    def line_of(self, j: int) -> int:
        return self.T[max(0, min(j, len(self.T) - 1))][2]

    def flow_graph(self, a: int, b: int) -> FlowGraph | None:
        """Grafo de fluxo de execucao (if/when/loop/try) do corpo [a,b). None se nao houver
        nada digno de grafo (a maioria das funcoes: so instrucoes lineares, sem ramo/loop) ou
        se o corpo estourar MAX_FLOW_NODES (funcao patologica — melhor nao ter grafo do que ter
        um grafo gigante e inutil). Nunca levanta: um bug aqui nao pode derrubar o parse do
        resto do arquivo."""
        try:
            g = _FlowBuilder(self).build(a, b)
        except Exception:  # noqa: BLE001 - construtor de grafo novo, ainda sem historico de robustez
            return None
        # so entry/return/throw/exit -> nenhum ramo, loop ou marcador de verdade, nao vale grafo
        if g and any(n["kind"] not in ("entry", "return", "throw", "exit") for n in g["nodes"]):
            return g
        return None


class KtParser(Parser):
    def parse(self) -> dict:
        T = self.T
        n = len(T)
        i = 0
        # cabecalho: annotations de arquivo, package, imports
        while i < n:
            k, s = T[i][0], T[i][1]
            if k == "sym" and s == "@" and i + 2 < n and T[i + 1][1] == "file" and T[i + 2][1] == ":":
                i, _ = self.parse_annot(i, n)
            elif k == "id" and s == "package":
                i, self.package = self._qname(i + 1, n)
            elif k == "id" and s == "import":
                i = self._import(i + 1, n)
            elif k == "sym" and s == ";":
                i += 1
            else:
                break
        self.members(i, n, -1)
        return self.result()

    def result(self) -> dict:
        return {"package": self.package, "imports": self.imports, "syms": self.syms}

    def _qname(self, i: int, n: int):
        T = self.T
        parts, ln = [], T[i][2] if i < n else 0
        while i < n and T[i][2] == ln and (T[i][0] == "id" or T[i][1] == "."):
            if T[i][0] == "id":
                parts.append(T[i][1])
            i += 1
        return i, ".".join(parts)

    def _import(self, i: int, n: int) -> int:
        T = self.T
        ln = T[i][2] if i < n else 0
        parts, alias, wild = [], "", False
        while i < n and T[i][2] == ln:
            k, s = T[i][0], T[i][1]
            if k == "id" and s == "as" and i + 1 < n:
                alias = T[i + 1][1]
                i += 2
                continue
            if k == "id":
                parts.append(s)
            elif s == "*":
                wild = True
            elif s == ";":
                i += 1
                break
            i += 1
        if parts:
            self.imports.append([".".join(parts), alias, wild])
        return i

    # ---- membros ----
    def members(self, i: int, end: int, owner: int, enum_body: bool = False, otp=frozenset()) -> None:
        T = self.T
        if enum_body:
            i = self.enum_entries(i, end, owner)
        last_prop = -1
        while i < end:
            t = T[i]
            if t[0] == "sym" and t[1] in (";", ","):
                i += 1
                continue
            doc = kdoc_summary(t[3])
            annots: list[str] = []
            mods: list[str] = []
            while i < end:
                t = T[i]
                if t[0] == "sym" and t[1] == "@":
                    i, a = self.parse_annot(i, end)
                    if a:
                        annots.append(a)
                elif t[0] == "id" and t[1] in MODS and i + 1 < end and (T[i + 1][0] == "id" or T[i + 1][1] == "@"):
                    mods.append(t[1])
                    i += 1
                else:
                    break
            if i >= end:
                break
            t = T[i]
            s = t[1]
            if t[0] != "id":
                i += 1
                continue
            if s in ("class", "interface", "object"):
                i = self.type_decl(i, end, mods, annots, doc, owner, otp)
                last_prop = -1
            elif s == "fun" and i + 1 < end and T[i + 1][1] == "interface":
                i = self.type_decl(i + 1, end, mods + ["fun"], annots, doc, owner, otp)
                last_prop = -1
            elif s == "fun":
                i = self.fun_decl(i, end, mods, annots, doc, owner, otp)
                last_prop = -1
            elif s in ("val", "var"):
                i, last_prop = self.prop_decl(i, end, mods, annots, doc, owner, otp)
            elif s == "typealias":
                line = t[2]
                nm = T[i + 1][1] if i + 1 < end else "?"
                j = self.scan_expr_end(i + 2, end)
                self.new_sym(kind="typealias", name=nm, line=line, end=self.line_of(j - 1), mods=mods, annots=annots, doc=doc, owner=owner, sig=ttext(T[i + 2:j]))
                i = j
                last_prop = -1
            elif s == "constructor" and owner >= 0:
                i = self.ctor_decl(i, end, mods, annots, doc, owner, otp)
            elif s == "init" and i + 1 < end and T[i + 1][1] == "{" and owner >= 0:
                c = self.match_pair(i + 1)
                self.extract_refs(i + 2, c, otp, self.syms[owner])
                i = c + 1
            elif s in ("get", "set") and last_prop >= 0 and i + 1 < end and T[i + 1][1] in ("(", "{", "="):
                i = self.accessor(i, end, last_prop, otp)
            else:
                i += 1

    def enum_entries(self, i: int, end: int, owner: int) -> int:
        T = self.T
        while i < end:
            t = T[i]
            if t[0] == "sym" and t[1] == "@":
                i, _ = self.parse_annot(i, end)
                continue
            if t[0] != "id" or t[1] in MODS or t[1] in ("fun", "val", "var", "class", "object", "interface", "init", "constructor", "typealias"):
                break
            j = i + 1
            if j < end and T[j][1] == "(":
                j = self.match_pair(j) + 1
            if j < end and T[j][1] == "{":
                j = self.match_pair(j) + 1
            self.new_sym(kind="enum_entry", name=t[1], line=t[2], end=self.line_of(j - 1), owner=owner)
            i = j
            if i < end and T[i][1] == ",":
                i += 1
                continue
            if i < end and T[i][1] == ";":
                return i + 1
            break
        return i

    def type_decl(self, i: int, end: int, mods, annots, doc, owner: int, otp) -> int:
        T = self.T
        kw = T[i][1]
        line = T[i][2]
        i += 1
        kind = kw
        if kw == "class":
            for m, lab in (("enum", "enum"), ("annotation", "annotation"), ("value", "value class"), ("data", "data class")):
                if m in mods:
                    kind = lab
                    break
        if kw == "object" and "companion" in mods:
            kind = "companion"
        name = ""
        if i < end and T[i][0] == "id" and T[i][1] not in ("where",):
            name = T[i][1]
            i += 1
        elif kw == "object":
            name = "Companion" if "companion" in mods else "<anonymous>"
        tp = set(otp)
        if i < end and T[i][1] == "<" and T[i][0] == "sym":
            ntp, i = self.parse_tparams(i)
            tp |= ntp
        idx = self.new_sym(kind=kind, name=name, line=line, mods=mods, annots=annots, doc=doc, owner=owner, tparams=sorted(tp))
        sym = self.syms[idx]
        types = set()
        # construtor primario
        while i < end and ((T[i][0] == "sym" and T[i][1] == "@") or (T[i][0] == "id" and T[i][1] in ("private", "internal", "public", "protected", "constructor"))):
            if T[i][1] == "@":
                i, a = self.parse_annot(i, end)
                if a:
                    sym["annots"].append("ctor:" + a)
            else:
                i += 1
        if i < end and T[i][0] == "sym" and T[i][1] == "(":
            close = self.match_pair(i)
            params = self.params(i + 1, close)
            sym["sig"] = "(" + ", ".join(p["text"] for p in params) + ")"
            for p in params:
                sym["inject"] += dotted_refs(p["toks"], tp)
                types.update(dotted_refs(p["toks"], tp))
                for pa in p.get("annots", []):
                    if ann_name_lite(pa) in ("Value", "Qualifier", "ConfigurationProperties"):
                        sym["annots"].append("param:" + pa)
                if p["prop"]:
                    self.new_sym(kind="property", name=p["name"], line=p["line"], end=p["line"], mods=([p["vis"]] if p["vis"] != "public" else []) + [p["prop"]], owner=idx, ptype=p["type"], sig=": " + p["type"] if p["type"] else "", types=sorted(dotted_refs(p["toks"], tp)), annots=list(p.get("annots", [])))
                    self.syms[-1]["mods"] = [m for m in self.syms[-1]["mods"] if m in ("private", "protected", "internal")]
                    self.syms[-1]["vk"] = p["prop"]
                    self.syms[-1]["vis"] = p["vis"]
                if p["default"]:
                    pass
            sym["params"] = [[p["name"], p["type"], p["annots"]] for p in params]
            i = close + 1
        # supertipos
        if i < end and T[i][0] == "sym" and T[i][1] == ":":
            i += 1
            i = self.supertypes(i, end, sym, tp, types)
        if i < end and T[i][1] == "where" and T[i][0] == "id":
            i = self.scan_type(i + 1, end, {"{"})
        sym["end"] = self.line_of(i - 1) if i > 0 else line
        if i < end and T[i][0] == "sym" and T[i][1] == "{":
            c = self.match_pair(i)
            self.members(i + 1, c, idx, enum_body=(kind == "enum"), otp=frozenset(tp))
            sym["end"] = T[c][2]
            i = c + 1
        sym["types"] = sorted(set(sym["types"]) | types)
        return i

    def supertypes(self, i: int, end: int, sym: dict, tp, types: set) -> int:
        T = self.T
        while i < end:
            j, ang, first = i, 0, True
            start = i
            prev = None
            while j < end:
                k, s, ln, _ = T[j]
                if k == "sym":
                    if s == "<":
                        ang += 1
                    elif s == ">":
                        ang = max(0, ang - 1)
                    elif ang == 0 and s in ("(", "{", ","):
                        break
                elif k == "id" and ang == 0 and s in ("by", "where"):
                    break
                if not first and ang == 0 and prev is not None and ln > prev[2] and prev[1] not in (",", ".", ":") and s not in (".", ",", "<"):
                    break
                first = False
                prev = T[j]
                j += 1
            refs = dotted_refs(T[start:j], tp)
            if refs:
                sym["supers"].append(refs[0])
                types.update(refs)
            if j < end and T[j][0] == "sym" and T[j][1] == "(":
                c = self.match_pair(j)
                if refs:
                    sym["super_calls"].append(refs[0])
                self.extract_refs(j + 1, c, tp, sym)
                j = c + 1
            if j < end and T[j][0] == "id" and T[j][1] == "by":
                d = j + 1
                dep = 0
                pv = None
                while d < end:
                    k, s, ln, _ = T[d]
                    if k == "sym":
                        if s in OPEN:
                            if s == "{" and dep == 0:
                                break
                            dep += 1
                        elif s in CLOSE:
                            dep -= 1
                        elif s == "," and dep == 0:
                            break
                    if dep == 0 and pv is not None and ln > pv[2] and pv[1] not in (".", ","):
                        break
                    pv = T[d]
                    d += 1
                self.extract_refs(j + 1, d, tp, sym)
                j = d
            if j < end and T[j][0] == "sym" and T[j][1] == ",":
                i = j + 1
                continue
            return j
        return i

    def params(self, a: int, close: int) -> list[dict]:
        T = self.T
        res = []
        k = a
        while k < close:
            e = self.find_comma(k, close)
            toks = T[k:e]
            p = self._param(toks)
            if p:
                res.append(p)
            k = e + 1
        return res

    def _param(self, toks) -> dict | None:
        if not toks:
            return None
        i, n = 0, len(toks)
        prop, vis = "", "public"
        pannots: list[str] = []
        while i < n:
            k, s = toks[i][0], toks[i][1]
            if k == "sym" and s == "@":
                i += 1
                if i < n and toks[i][1] in USE_SITES and i + 1 < n and toks[i + 1][1] == ":":
                    i += 2
                name_parts = []
                while i < n and toks[i][0] == "id":
                    name_parts.append(toks[i][1])
                    if i + 2 < n and toks[i + 1][1] == "." and toks[i + 2][0] == "id":
                        i += 2
                        continue
                    i += 1
                    break
                args = ""
                if i < n and toks[i][1] == "(" and toks[i][0] == "sym":
                    d, a0 = 0, i
                    while i < n:
                        if toks[i][0] == "sym" and toks[i][1] == "(":
                            d += 1
                        elif toks[i][0] == "sym" and toks[i][1] == ")":
                            d -= 1
                            if d == 0:
                                i += 1
                                break
                        i += 1
                    args = ttext(toks[a0 + 1:i - 1])
                if name_parts:
                    pannots.append(name_parts[-1] + (f"({args[:160]})" if args else ""))
            elif k == "id" and s in ("val", "var"):
                prop = s
                i += 1
            elif k == "id" and s in ("private", "protected", "internal", "public"):
                vis = s
                i += 1
            elif k == "id" and s in ("vararg", "noinline", "crossinline", "override", "final", "open", "lateinit"):
                i += 1
            else:
                break
        if i >= n or toks[i][0] != "id":
            return None
        name, line = toks[i][1], toks[i][2]
        i += 1
        typ_toks, default = [], False
        if i < n and toks[i][1] == ":":
            j = i + 1
            depth = 0
            while j < n:
                if toks[j][0] == "sym":
                    if toks[j][1] in ("(", "[", "<"):
                        depth += 1
                    elif toks[j][1] in (")", "]", ">"):
                        depth -= 1
                    elif toks[j][1] == "=" and depth == 0:
                        default = True
                        break
                j += 1
            typ_toks = toks[i + 1:j]
        elif i < n and toks[i][1] == "=":
            default = True
        typ = ttext(typ_toks)
        text = (f"{name}: {typ}" if typ else name) + (" = ..." if default else "")
        return {"name": name, "type": typ, "toks": typ_toks, "prop": prop, "vis": vis, "default": default,
                "line": line, "text": text, "annots": pannots}

    def fun_decl(self, i: int, end: int, mods, annots, doc, owner: int, otp) -> int:
        T = self.T
        line = T[i][2]
        i += 1
        tp = set(otp)
        own_tp: set = set()
        if i < end and T[i][0] == "sym" and T[i][1] == "<":
            own_tp, i = self.parse_tparams(i)
            tp |= own_tp
        j, ang, hs = i, 0, i
        while j < end:
            k, s = T[j][0], T[j][1]
            if k == "sym":
                if s == "<":
                    ang += 1
                elif s == ">":
                    ang = max(0, ang - 1)
                elif s == "(" and ang == 0:
                    break
                elif s in ("{", "}", ";", "="):
                    return j + 1
            j += 1
        if j >= end:
            return end
        hdr = T[hs:j]
        ni = max((x for x in range(len(hdr)) if hdr[x][0] == "id"), default=-1)
        if ni < 0:
            return j + 1
        name = hdr[ni][1]
        rt = hdr[:ni]
        recv = ""
        if rt:
            last = rt[-1][1]
            recv = ttext(rt[:-1]) + ("?" if last == "?." else "")
        close = self.match_pair(j)
        params = self.params(j + 1, close)
        k = close + 1
        ret = ""
        if k < end and T[k][0] == "sym" and T[k][1] == ":":
            e = self.scan_type(k + 1, end, {"{", "=", "where"})
            ret = ttext(T[k + 1:e])
            rtoks = T[k + 1:e]
            k = e
        else:
            rtoks = []
        if k < end and T[k][0] == "id" and T[k][1] == "where":
            k = self.scan_type(k + 1, end, {"{", "="})
        sig = "(" + ", ".join(p["text"] for p in params) + ")" + (f": {ret}" if ret else "")
        idx = self.new_sym(kind="fun", name=name, line=line, mods=mods, annots=annots, doc=doc, owner=owner, sig=sig, recv=recv, ret=ret,
                           params=[[p["name"], p["type"], p["annots"]] for p in params], tparams=sorted(own_tp))
        sym = self.syms[idx]
        tys = set()
        for p in params:
            tys.update(dotted_refs(p["toks"], tp))
        tys.update(dotted_refs(rtoks, tp))
        if recv:
            tys.update(dotted_refs(rt[:-1], tp))
        sym["types"] = sorted(tys)
        body = None
        if k < end and T[k][0] == "sym" and T[k][1] == "{":
            c = self.match_pair(k)
            body = (k + 1, c)
            sym["end"] = T[c][2]
            k = c + 1
        elif k < end and T[k][0] == "sym" and T[k][1] == "=":
            e = self.scan_expr_end(k + 1, end)
            body = (k + 1, e)
            sym["end"] = self.line_of(e - 1)
            k = e
        else:
            sym["end"] = self.line_of(k - 1)
        if body:
            self.extract_refs(body[0], body[1], tp, sym)
            sym["cc"] = self.complexity(body[0], body[1])
            sym["fp"], sym["ntok"] = self.fingerprint(body[0], body[1])
            fg = self.flow_graph(body[0], body[1])
            if fg:
                sym["flow"] = fg
        return k

    def ctor_decl(self, i: int, end: int, mods, annots, doc, owner: int, otp) -> int:
        T = self.T
        line = T[i][2]
        i += 1
        if i >= end or T[i][1] != "(":
            return i
        close = self.match_pair(i)
        params = self.params(i + 1, close)
        k = close + 1
        osym = self.syms[owner]
        idx = self.new_sym(kind="constructor", name=osym["name"], line=line, mods=mods, annots=annots, doc=doc, owner=owner,
                           sig="(" + ", ".join(p["text"] for p in params) + ")", params=[[p["name"], p["type"], p["annots"]] for p in params])
        sym = self.syms[idx]
        sym["types"] = sorted({t for p in params for t in dotted_refs(p["toks"], otp)})
        if k < end and T[k][1] == ":" and T[k][0] == "sym":
            e = k + 1
            if e < end and T[e][1] in ("this", "super") and e + 1 < end and T[e + 1][1] == "(":
                k = self.match_pair(e + 1) + 1
            else:
                k = e
        if k < end and T[k][1] == "{" and T[k][0] == "sym":
            c = self.match_pair(k)
            self.extract_refs(k + 1, c, otp, sym)
            sym["end"] = T[c][2]
            k = c + 1
        else:
            sym["end"] = self.line_of(k - 1)
        return k

    def prop_decl(self, i: int, end: int, mods, annots, doc, owner: int, otp):
        T = self.T
        kw = T[i][1]
        line = T[i][2]
        i += 1
        tp = set(otp)
        if i < end and T[i][0] == "sym" and T[i][1] == "<":
            ntp, i = self.parse_tparams(i)
            tp |= ntp
        if i < end and T[i][0] == "sym" and T[i][1] == "(":
            c = self.match_pair(i)
            k = c + 1
            if k < end and T[k][1] in ("=",):
                k = self.scan_expr_end(k + 1, end)
            return k, -1
        k = i
        while k < end and T[k][2] == line and not (T[k][0] == "sym" and T[k][1] in (":", "=", ";", "{", "}")) and not (T[k][0] == "id" and T[k][1] == "by" and k > i):
            k += 1
        hdr = T[i:k]
        ni = max((x for x in range(len(hdr)) if hdr[x][0] == "id"), default=-1)
        if ni < 0:
            return max(k, i + 1), -1
        name = hdr[ni][1]
        recv = ttext(hdr[:ni - 1]) if ni >= 2 else ""
        ptype, tys = "", set()
        if k < end and T[k][0] == "sym" and T[k][1] == ":":
            e = self.scan_type(k + 1, end, {"=", ";", "by", "{", "get", "set"})
            ptype = ttext(T[k + 1:e])
            tys.update(dotted_refs(T[k + 1:e], tp))
            k = e
        body = None
        if k < end and ((T[k][0] == "sym" and T[k][1] == "=") or (T[k][0] == "id" and T[k][1] == "by")):
            e = self.scan_expr_end(k + 1, end)
            body = (k + 1, e)
            if not ptype and T[k][1] == "=" and k + 2 < e and T[k + 1][0] == "id" and T[k + 1][1][:1].isupper() and T[k + 2][1] in ("(", "."):
                ptype = T[k + 1][1]
            k = e
        idx = self.new_sym(kind="property", name=name, line=line, end=self.line_of(k - 1), mods=mods, annots=annots, doc=doc, owner=owner,
                           sig=(": " + ptype) if ptype else "", ptype=ptype, recv=recv, types=sorted(tys))
        self.syms[idx]["vk"] = kw
        if body:
            self.extract_refs(body[0], body[1], tp, self.syms[idx])
        return k, idx

    def accessor(self, i: int, end: int, prop: int, otp) -> int:
        T = self.T
        k = i + 1
        if T[k][1] == "(":
            k = self.match_pair(k) + 1
        if k < end and T[k][1] == ":" and T[k][0] == "sym":
            k = self.scan_type(k + 1, end, {"{", "="})
        sym = self.syms[prop]
        if k < end and T[k][1] == "{" and T[k][0] == "sym":
            c = self.match_pair(k)
            self.extract_refs(k + 1, c, otp, sym)
            sym["end"] = max(sym["end"], T[c][2])
            return c + 1
        if k < end and T[k][1] == "=" and T[k][0] == "sym":
            e = self.scan_expr_end(k + 1, end)
            self.extract_refs(k + 1, e, otp, sym)
            sym["end"] = max(sym["end"], self.line_of(e - 1))
            return e
        return k


# =========================================================================== #
# Parser Java (nivel de tipos/membros; suficiente para o grafo em projetos mistos)
# =========================================================================== #
class JavaParser(KtParser):
    def parse(self) -> dict:
        T = self.T
        n = len(T)
        i = 0
        while i < n:
            k, s = T[i][0], T[i][1]
            if k == "id" and s == "package":
                i, self.package = self._qname(i + 1, n)
            elif k == "id" and s == "import":
                i = self._import(i + 1, n)
                if self.imports and self.imports[-1][0].startswith("static."):
                    self.imports[-1][0] = self.imports[-1][0][7:]
            elif k == "sym" and s == ";":
                i += 1
            else:
                break
        self.jmembers(i, n, -1, frozenset())
        return self.result()

    def jmembers(self, i: int, end: int, owner: int, tp) -> None:
        T = self.T
        while i < end:
            t = T[i]
            if t[0] == "sym" and t[1] == ";":
                i += 1
                continue
            doc = kdoc_summary(t[3])
            annots: list[str] = []
            mods: list[str] = []
            while i < end:
                t = T[i]
                if t[0] == "sym" and t[1] == "@" and not (i + 1 < end and T[i + 1][1] == "interface"):
                    i, a = self.parse_annot(i, end)
                    if a:
                        annots.append(a)
                elif t[0] == "id" and t[1] in JAVA_MODS:
                    mods.append(t[1])
                    i += 1
                elif t[0] == "id" and t[1] == "non" and i + 2 < end and T[i + 1][1] == "-":
                    i += 3
                else:
                    break
            if i >= end:
                break
            t = T[i]
            s = t[1]
            if t[0] == "sym" and s == "@" and i + 1 < end and T[i + 1][1] == "interface":
                i = self.jtype(i + 1, end, "@interface", mods, annots, doc, owner, tp)
            elif t[0] == "id" and s in ("class", "interface", "enum", "record") and i + 1 < end and T[i + 1][0] == "id":
                i = self.jtype(i, end, s, mods, annots, doc, owner, tp)
            elif t[0] == "sym" and s == "{":
                i = self.match_pair(i) + 1
            else:
                i = self.jmember(i, end, mods, annots, doc, owner, tp)

    def jparams(self, a: int, close: int) -> list[dict]:
        T = self.T
        res = []
        k = a
        while k < close:
            e = self.find_comma(k, close)
            toks = [x for x in T[k:e]]
            k = e + 1
            # remove annotations e 'final' (mas guarda o nome da anotacao antes de descartar)
            clean, pannots, i = [], [], 0
            while i < len(toks):
                if toks[i][1] == "@" and toks[i][0] == "sym":
                    i += 1
                    if i < len(toks) and toks[i][0] == "id":
                        pannots.append(toks[i][1])
                        i += 1
                    if i < len(toks) and toks[i][1] == "(" and toks[i][0] == "sym":
                        d = 0
                        while i < len(toks):
                            if toks[i][1] == "(":
                                d += 1
                            elif toks[i][1] == ")":
                                d -= 1
                                if d == 0:
                                    i += 1
                                    break
                            i += 1
                    continue
                if toks[i][0] == "id" and toks[i][1] == "final":
                    i += 1
                    continue
                clean.append(toks[i])
                i += 1
            ids = [x for x in range(len(clean)) if clean[x][0] == "id"]
            if len(ids) < 2 and not (ids and len(clean) > 1):
                continue
            ni = ids[-1]
            typ_toks = clean[:ni]
            typ = ttext(typ_toks)
            res.append({"name": clean[ni][1], "type": typ, "toks": typ_toks, "prop": "", "vis": "public", "default": False,
                        "line": clean[ni][2], "text": f"{clean[ni][1]}: {typ}", "annots": pannots})
        return res

    def jtype(self, i: int, end: int, kw: str, mods, annots, doc, owner: int, otp) -> int:
        T = self.T
        line = T[i][2]
        i += 1
        name = T[i][1] if i < end else "?"
        i += 1
        tp = set(otp)
        if i < end and T[i][0] == "sym" and T[i][1] == "<":
            ntp, i = self.parse_tparams(i)
            tp |= ntp
        kind = {"class": "class", "interface": "interface", "enum": "enum", "record": "data class"}.get(kw, "annotation")
        if kind == "class" and "abstract" in mods:
            kind = "abstract class"
        idx = self.new_sym(kind=kind, name=name, line=line, mods=mods, annots=annots, doc=doc, owner=owner, tparams=sorted(tp))
        sym = self.syms[idx]
        types: set[str] = set()
        if kw == "record" and i < end and T[i][1] == "(":
            close = self.match_pair(i)
            params = self.jparams(i + 1, close)
            sym["sig"] = "(" + ", ".join(p["text"] for p in params) + ")"
            sym["params"] = [[p["name"], p["type"], p["annots"]] for p in params]
            for p in params:
                r = dotted_refs(p["toks"], tp)
                sym["inject"] += r
                types.update(r)
                self.new_sym(kind="property", name=p["name"], line=p["line"], end=p["line"], owner=idx, ptype=p["type"], sig=": " + p["type"], types=r, vk="val")
            i = close + 1
        while i < end and not (T[i][0] == "sym" and T[i][1] == "{"):
            if T[i][0] == "id" and T[i][1] in ("extends", "implements", "permits"):
                role = T[i][1]
                j, ang, start = i + 1, 0, i + 1
                chunks: list[list] = []
                while j < end:
                    k, s = T[j][0], T[j][1]
                    if k == "sym" and s == "{":
                        break
                    if k == "id" and s in ("extends", "implements", "permits") and ang == 0:
                        break
                    if k == "sym":
                        if s == "<":
                            ang += 1
                        elif s == ">":
                            ang = max(0, ang - 1)
                        elif s == "," and ang == 0:
                            chunks.append(T[start:j])
                            start = j + 1
                    j += 1
                chunks.append(T[start:j])
                for ch in chunks:
                    r = dotted_refs(ch, tp)
                    if r:
                        types.add(r[0])
                        if role != "permits":
                            sym["supers"].append(r[0])
                i = j
            else:
                i += 1
        sym["end"] = self.line_of(i - 1)
        if i < end and T[i][1] == "{":
            c = self.match_pair(i)
            j = i + 1
            if kind == "enum":
                j = self.enum_entries(j, c, idx)
            self.jmembers(j, c, idx, frozenset(tp))
            sym["end"] = T[c][2]
            i = c + 1
        sym["types"] = sorted(set(sym["types"]) | types)
        return i

    def jmember(self, i: int, end: int, mods, annots, doc, owner: int, tp) -> int:
        T = self.T
        line = T[i][2]
        tps = set(tp)
        if T[i][0] == "sym" and T[i][1] == "<":
            ntp, i = self.parse_tparams(i)
            tps |= ntp
        j, ang = i, 0
        while j < end:
            k, s = T[j][0], T[j][1]
            if k == "sym":
                if s == "<":
                    ang += 1
                elif s == ">":
                    ang = max(0, ang - 1)
                elif ang == 0 and s in ("(", "=", ";", "{", "}"):
                    break
            j += 1
        if j >= end:
            return end
        if T[j][1] == "}":
            return j + 1
        hdr = T[i:j]
        ids = [x for x in range(len(hdr)) if hdr[x][0] == "id"]
        if not ids:
            return j + 1
        ni = ids[-1]
        name = hdr[ni][1]
        ret = ttext(hdr[:ni])
        if T[j][1] == "(" and T[j][0] == "sym":
            close = self.match_pair(j)
            params = self.jparams(j + 1, close)
            k = close + 1
            while k < end and not (T[k][0] == "sym" and T[k][1] in ("{", ";")):
                k += 1
            is_ctor = owner >= 0 and name == self.syms[owner]["name"] and not ret
            idx = self.new_sym(kind="constructor" if is_ctor else "fun", name=name, line=line, mods=mods, annots=annots, doc=doc,
                               owner=owner, sig="(" + ", ".join(p["text"] for p in params) + ")" + (f": {ret}" if ret and not is_ctor else ""),
                               ret=ret, params=[[p["name"], p["type"], p["annots"]] for p in params], tparams=sorted(tps))
            sym = self.syms[idx]
            tys = set()
            for p in params:
                tys.update(dotted_refs(p["toks"], tps))
            tys.update(dotted_refs(hdr[:ni], tps))
            sym["types"] = sorted(tys)
            if k < end and T[k][1] == "{":
                c = self.match_pair(k)
                self.extract_refs(k + 1, c, tps, sym)
                sym["cc"] = self.complexity(k + 1, c)
                sym["fp"], sym["ntok"] = self.fingerprint(k + 1, c)
                fg = self.flow_graph(k + 1, c)
                if fg:
                    sym["flow"] = fg
                sym["end"] = T[c][2]
                return c + 1
            sym["end"] = self.line_of(k)
            return k + 1
        k, d = j, 0
        while k < end:
            if T[k][0] == "sym":
                if T[k][1] in OPEN:
                    d += 1
                elif T[k][1] in CLOSE:
                    d -= 1
                elif T[k][1] == ";" and d <= 0:
                    break
            k += 1
        idx = self.new_sym(kind="property", name=name, line=line, end=self.line_of(k), mods=mods, annots=annots, doc=doc, owner=owner,
                           ptype=ret, sig=(": " + ret) if ret else "", types=sorted(dotted_refs(hdr[:ni], tps)), vk="val" if "final" in mods else "var")
        if T[j][1] == "=":
            self.extract_refs(j + 1, k, tps, self.syms[idx])
        return k + 1


_TODO = re.compile(r"(?://|/\*|\*)\s*.*?\b(TODO|FIXME|HACK)\b[:\s]*(.*)")


def decode_bytes(raw: bytes) -> str | None:
    if b"\0" in raw[:4096]:
        return None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def parse_source(text: str, rel: str, lang: str) -> dict:
    """Parseia um arquivo. Nunca levanta: em erro devolve o que conseguiu."""
    err = ""
    data: dict = {"package": "", "imports": [], "syms": []}
    try:
        p = (JavaParser if lang == "java" else KtParser)(text, rel)
        try:
            data = p.parse()
        except Exception as e:  # noqa: BLE001 - parser heuristico: preserva parcial
            err = f"{type(e).__name__}: {e}"
            data = p.result()
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    todos = []
    if "TODO" in text or "FIXME" in text or "HACK" in text:
        for ln, line in enumerate(text.splitlines(), 1):
            if "TODO" in line or "FIXME" in line or "HACK" in line:
                m = _TODO.search(line)
                if m:
                    todos.append([ln, f"{m.group(1)} {m.group(2).strip()}"[:100]])
    data.update({"lang": lang, "loc": text.count("\n") + 1, "todos": todos[:20], "n_todos": len(todos), "err": err})
    return data


def parse_task(task):
    """Executado em processos filhos. task=(rel, abs_path, lang) -> (rel, sha, data)."""
    rel, path, lang = task
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return rel, "", None
    sha = hashlib.sha1(raw).hexdigest()
    text = decode_bytes(raw)
    if text is None:
        return rel, sha, None
    return rel, sha, parse_source(text, rel, lang)


# =========================================================================== #
# Configuracao, ignore e descoberta de arquivos
# =========================================================================== #
def load_config(root: Path) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    for p in (Path.home() / ".claude-indexer.json", root / ".claude-indexer.json"):
        try:
            if p.is_file():
                user = json.loads(p.read_text(encoding="utf-8"))
                for k, v in user.items():
                    if k not in DEFAULT_CONFIG:
                        warn(f"{p}: chave desconhecida '{k}' (ignorada; confira o nome)")
                        continue
                    default = DEFAULT_CONFIG[k]
                    if not isinstance(v, type(default)) and not (isinstance(v, (int, float)) and isinstance(default, (int, float))):
                        warn(f"{p}: '{k}' deveria ser {type(default).__name__}, veio {type(v).__name__} (ignorado)")
                        continue
                    if k in ("ignore", "entry_annotations", "entry_interfaces", "reactive_wrappers",
                              "dead_ignore_annotations", "layers") and isinstance(v, list):
                        cfg[k] = cfg.get(k, []) + v
                    else:
                        cfg[k] = v
        except (OSError, ValueError) as e:
            warn(f"config invalida {p}: {e}")
    ign = root / ".claude-indexer-ignore"
    if ign.is_file():
        try:
            cfg["ignore"] += [ln.strip() for ln in ign.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
        except OSError:
            pass
    return cfg


def is_ignored(posix: str, patterns: list[str]) -> bool:
    parts = posix.split("/")
    for pat in patterns:
        dir_only = pat.endswith("/")
        p = pat.strip("/")
        if not p:
            continue
        if "/" in p:
            if fnmatch.fnmatch(posix, p) or posix.startswith(p + "/") or fnmatch.fnmatch(posix, p + "/*"):
                return True
        elif dir_only:
            if any(fnmatch.fnmatch(x, p) for x in parts[:-1]):
                return True
        elif any(fnmatch.fnmatch(x, p) for x in parts):
            return True
    return False


GENERATED_NAMES = {"CLAUDE.md", "AGENTS.md", "WORKSPACE-INDEX.md", Path(__file__).name}


def generated_paths(cfg: dict) -> tuple:
    d = cfg["docs_dir"]
    return (f"{d}/api/", f"{d}/graph/", f"{d}/index/", f"{d}/INDEX.md", f"{d}/ANALYSIS.md", f"{d}/ENDPOINTS.md",
            f"{d}/FLOWS.md", f"{d}/TREE.md", cfg["state_dir"] + "/")


def list_files(root: Path, cfg: dict) -> list[tuple[str, int]]:
    """Todos os arquivos (relativos, posix) com tamanho, respeitando .gitignore e config."""
    cand: list[str] = []
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "-c", "-o", "--exclude-standard"],
                             capture_output=True, check=True, timeout=180).stdout.decode("utf-8", "replace")
        cand = [p for p in out.split("\0") if p]
    except Exception:  # noqa: BLE001 - sem git: percorre a arvore
        cand = []
    if not cand:
        seen_dirs: set = set()
        for dp, dn, fn in os.walk(root, followlinks=False, onerror=lambda e: None):
            try:
                real = os.path.realpath(dp)
            except OSError:
                continue
            if real in seen_dirs:
                dn[:] = []
                continue
            seen_dirs.add(real)
            dn[:] = sorted(d for d in dn if d not in DEFAULT_IGNORE_DIRS)
            base = Path(dp).relative_to(root)
            cand += [(base / f).as_posix() for f in fn]
    gen = generated_paths(cfg)
    res, seen = [], set()
    for posix in cand:
        if posix in seen:
            continue
        seen.add(posix)
        parts = posix.split("/")
        if any(x in DEFAULT_IGNORE_DIRS for x in parts[:-1]):
            continue
        if posix.startswith(gen) or parts[-1] in GENERATED_NAMES or is_ignored(posix, cfg["ignore"]):
            continue
        low = "/" + posix
        if parts[-1] in GENERATED_FILE_NAMES or any(h in low for h in GENERATED_HINTS):
            continue
        try:
            st = (root / posix).stat()
        except OSError:
            continue
        if os.path.isfile(root / posix):
            res.append((posix, st.st_size))
    return sorted(res)


# =========================================================================== #
# Modulos e build (Gradle Kotlin/Groovy DSL, version catalog, Maven)
# =========================================================================== #
def read_text(path: Path, limit: int = MAX_BYTES) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return decode_bytes(path.read_bytes()) or ""
    except OSError:
        return ""


def parse_catalog(text: str) -> tuple[dict, str]:
    libs: dict[str, str] = {}
    section, kver = "", ""
    for line in text.splitlines():
        ln = line.strip()
        if ln.startswith("["):
            section = ln.strip("[] ")
            continue
        m = re.match(r'^([\w\-.]+)\s*=\s*(.+)$', ln)
        if not m:
            continue
        key, val = m.groups()
        if section == "versions" and key == "kotlin":
            mv = re.search(r'"([^"]+)"', val)
            kver = mv.group(1) if mv else kver
        if section == "libraries":
            alias = re.sub(r"[-_]", ".", key)
            mm = re.search(r'module\s*=\s*"([^"]+)"', val)
            if mm:
                libs[alias] = mm.group(1)
                continue
            g, a = re.search(r'group\s*=\s*"([^"]+)"', val), re.search(r'name\s*=\s*"([^"]+)"', val)
            if g and a:
                libs[alias] = f"{g.group(1)}:{a.group(1)}"
                continue
            ms = re.match(r'"([^":]+:[^":]+)(?::[^"]*)?"', val)
            if ms:
                libs[alias] = ms.group(1)
    return libs, kver


_CFG_RE = re.compile(
    r'\b((?:[a-z]\w*(?:Implementation|Api|Only)|implementation|api|kapt\w*|ksp\w*|annotationProcessor|classpath|compile|runtime|testCompile))'
    r'\s*[(\s]\s*([^\n;]*)')


def parse_gradle_build(text: str, catalog: dict) -> dict:
    ext, ext_t, proj, proj_t, typed, typed_t = set(), set(), set(), set(), set(), set()
    for m in _CFG_RE.finditer(text):
        test = "test" in m.group(1).lower()
        rest = m.group(2)
        for pm in re.finditer(r'project\(\s*(?:path\s*=\s*)?["\'](:[^"\']+)["\']', rest):
            (proj_t if test else proj).add(pm.group(1))
        for tm in re.finditer(r'\bprojects\.([\w.]+)', rest):
            (typed_t if test else typed).add(tm.group(1))
        for sm in re.finditer(r'["\']([\w.\-]+:[\w.\-]+)(?::[^"\']*)?["\']', rest):
            (ext_t if test else ext).add(sm.group(1))
        for lm in re.finditer(r'\blibs\.(?!plugins|versions|bundles)([\w.]+)', rest):
            alias = lm.group(1)
            hit = catalog.get(alias)
            if hit is None:
                for k, v in catalog.items():
                    if alias.startswith(k):
                        hit = v
                        break
            (ext_t if test else ext).add(hit or f"libs.{alias}")
    plugins = set(re.findall(r'\bid\s*\(?\s*["\']([^"\']+)["\']', text))
    plugins |= {"org.jetbrains.kotlin." + p for p in re.findall(r'\bkotlin\(\s*["\']([\w\-]+)["\']\s*\)', text)}
    plugins |= set(re.findall(r'apply\s+plugin:\s*["\']([^"\']+)["\']', text))
    plugins |= set(re.findall(r'^\s*(application|java-library|java|war|maven-publish)\s*$', text, re.M))
    return {"ext": ext, "ext_t": ext_t, "proj": proj, "proj_t": proj_t, "typed": typed, "typed_t": typed_t, "plugins": plugins}


def parse_pom(text: str) -> dict:
    import xml.etree.ElementTree as ET
    res = {"artifact": "", "modules": [], "ext": set(), "ext_t": set(), "packaging": "jar", "parent": ""}
    try:
        text = re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", text, count=3)
        r = ET.fromstring(text)
    except ET.ParseError:
        return res
    res["artifact"] = (r.findtext("artifactId") or "").strip()
    res["packaging"] = (r.findtext("packaging") or "jar").strip()
    res["modules"] = [m.text.strip() for m in r.findall("./modules/module") if m.text]
    for d in r.findall("./dependencies/dependency"):
        g, a = (d.findtext("groupId") or "").strip(), (d.findtext("artifactId") or "").strip()
        (res["ext_t"] if (d.findtext("scope") or "") == "test" else res["ext"]).add(f"{g}:{a}")
    return res


def norm_id(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_modules(root: Path, files: list[tuple[str, int]]) -> tuple[dict, dict]:
    """Retorna (modulos {dir: info}, info_projeto)."""
    fset = {p for p, _ in files}
    props = gradle_properties(root, fset)
    mods: dict[str, dict] = {}

    def mk(d: str, gid: str, kind: str) -> dict:
        m = mods.setdefault(d, {"dir": d, "id": gid, "kind": kind, "ext": set(), "ext_t": set(), "proj": set(), "plugins": set(),
                                 "proj_t": set(), "typed": set(), "typed_t": set(), "build": "", "artifact": ""})
        return m

    proj = {"name": "", "kotlin": "", "jvm": "", "spring_boot": "", "catalog": {}, "build_kind": "none",
            "maven": False, "properties": {}}
    catalog: dict[str, str] = {}
    for p, _ in files:
        if p.endswith("libs.versions.toml") or p.endswith(".versions.toml"):
            c, kv = parse_catalog(read_text(root / p))
            catalog.update(c)
            proj["kotlin"] = proj["kotlin"] or kv
    proj["catalog"] = catalog

    # settings.gradle(.kts)
    for name in ("settings.gradle.kts", "settings.gradle"):
        if name in fset:
            txt = read_text(root / name)
            proj["build_kind"] = "gradle"
            m = re.search(r'rootProject\.name\s*=\s*["\']([^"\']+)["\']', txt)
            proj["name"] = m.group(1) if m else ""
            for im in re.finditer(r'\binclude\s*\(?\s*((?:["\'][^"\']+["\']\s*,?\s*)+)', txt):
                for gp in re.findall(r'["\']([^"\']+)["\']', im.group(1)):
                    gp = gp if gp.startswith(":") else ":" + gp
                    mk(gp.strip(":").replace(":", "/"), gp, "gradle")
            break
    # build.gradle(.kts) e pom.xml
    poms: dict[str, dict] = {}
    for p, _ in files:
        base = p.rsplit("/", 1)[-1]
        d = p.rsplit("/", 1)[0] if "/" in p else "."
        if base in ("build.gradle.kts", "build.gradle"):
            if proj["build_kind"] == "none":
                proj["build_kind"] = "gradle"
            gid = ":" if d == "." else ":" + d.replace("/", ":")
            m = mk(d, gid, "gradle")
            txt = read_text(root / p)
            info = parse_gradle_build(txt, catalog)
            for k in ("ext", "ext_t", "proj", "proj_t", "typed", "typed_t", "plugins"):
                m[k] |= info[k]
            m["build"] = p
            if not proj["kotlin"]:
                mk_ = (re.search(r'kotlin\("jvm"\)\s+version\s+["\']([^"\']+)', txt)
                       or re.search(r'org\.jetbrains\.kotlin\.jvm["\']\)?\s+version\s+["\']([^"\']+)', txt)
                       or re.search(r'kotlin_version\s*=\s*["\']([^"\']+)', txt)
                       or re.search(r'kotlin-gradle-plugin:([\w.\-]+)', txt))
                proj["kotlin"] = mk_.group(1) if mk_ else ""
            if not proj["jvm"]:
                mj = (re.search(r"jvmToolchain\(\s*(\d+)", txt) or re.search(r"JavaVersion\.VERSION_(\d+)", txt)
                      or re.search(r"JvmTarget\.JVM_(\d+)", txt) or re.search(r'(?:jvmTarget|sourceCompatibility)\s*=\s*["\']?(?:1\.)?(\d+)', txt))
                proj["jvm"] = mj.group(1) if mj else ""
            if not proj["spring_boot"]:
                sb = re.search(r'org\.springframework\.boot["\']\)?\s+version\s+["\']([^"\']+)', txt)
                proj["spring_boot"] = sb.group(1) if sb else ""
        elif base == "pom.xml":
            info = parse_pom(read_text(root / p))
            poms[d] = info
            proj["maven"] = True
            if proj["build_kind"] == "none":
                proj["build_kind"] = "maven"
    for d, info in poms.items():
        gid = ":" if d == "." else ":" + (info["artifact"] or d.replace("/", "-"))
        m = mk(d, gid, "maven")
        m["ext"] |= info["ext"]
        m["ext_t"] |= info["ext_t"]
        m["artifact"] = info["artifact"]
        m["build"] = (d + "/pom.xml") if d != "." else "pom.xml"
        if d == "." and not proj["name"]:
            proj["name"] = info["artifact"]
    if "." not in mods:
        mk(".", ":", proj["build_kind"] if proj["build_kind"] != "none" else "dir")
    source_dirs_without_build(root, fset, mods)
    for d in list(mods):
        if d.split("/")[0] in ("buildSrc", "build-logic") or d.startswith("gradle/plugins"):
            mods.pop(d, None)
    try:
        apply_shared(mods, scan_shared_build(root, fset, catalog))
    except Exception as e:  # noqa: BLE001 - build exotico nao pode derrubar a indexacao
        warn(f"build compartilhado nao interpretado: {e}")
    proj["properties"] = {k: v for k, v in props.items() if "version" in k.lower() or "jvm" in k.lower()}
    if not proj["kotlin"]:
        for k, v in props.items():
            if k.lower().endswith("kotlin.version") or k.lower() == "kotlinversion":
                proj["kotlin"] = v
    # resolve dependencias entre modulos
    by_id = {m["id"]: d for d, m in mods.items()}
    by_norm = {norm_id(m["id"]): d for d, m in mods.items()}
    by_artifact = {m["artifact"]: d for d, m in mods.items() if m["artifact"]}
    for d, m in mods.items():
        for tk, out in (("typed", "deps"), ("typed_t", "deps_t")):
            m.setdefault(out, set())
            for acc in m[tk]:
                hit = by_norm.get(norm_id(acc))
                if hit:
                    m[out].add(mods[hit]["id"])
        m.setdefault("deps", set())
        m.setdefault("deps_t", set())
        for gp in m["proj"]:
            if gp in by_id:
                m["deps"].add(gp)
        for gp in m["proj_t"]:
            if gp in by_id:
                m["deps_t"].add(gp)
        for e in list(m["ext"]):
            a = e.split(":")[-1]
            if a in by_artifact and by_artifact[a] != d:
                m["deps"].add(mods[by_artifact[a]]["id"])
        m["deps"].discard(m["id"])
        m["deps_t"].discard(m["id"])
    return mods, proj


def module_of(path: str, mods: dict) -> str:
    d = path.rsplit("/", 1)[0] if "/" in path else "."
    while True:
        if d in mods:
            return d
        if d == ".":
            return "."
        d = d.rsplit("/", 1)[0] if "/" in d else "."


_SS_RE = re.compile(r"(?:^|/)src/([\w\-]+)/(?:kotlin|java|resources|scala)/")


def source_set(path: str) -> str:
    m = _SS_RE.search(path)
    return m.group(1) if m else ""


def is_test_path(path: str) -> bool:
    ss = source_set(path)
    if ss:
        return "test" in ss.lower()
    low = "/" + path.lower()
    return "/test/" in low or "/tests/" in low or low.endswith(("test.kt", "tests.kt", "test.java", "spec.kt"))


# =========================================================================== #
# Coleta (com cache incremental + paralelismo)
# =========================================================================== #
def load_cache(root: Path, cfg: dict) -> dict:
    p = root / cfg["state_dir"] / "cache.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("v") == PARSER_VERSION:
            return d.get("files", {})
    except (OSError, ValueError):
        pass
    return {}


def save_cache(root: Path, cfg: dict, files: dict) -> None:
    p = root / cfg["state_dir"] / "cache.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"v": PARSER_VERSION, "files": files}, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, p)


def is_build_script(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return base.endswith(".gradle.kts") or base in ("settings.gradle.kts", "build.gradle.kts")


def collect(root: Path, cfg: dict, full: bool = False, use_cache: bool = True, quiet: bool = False) -> dict:
    t0 = time.time()
    files = list_files(root, cfg)
    mods, proj = find_modules(root, files)
    cache = {} if (full or not use_cache) else load_cache(root, cfg)
    new_cache: dict = {}
    recs: list[dict] = []
    todo: list[tuple] = []
    for path, size in files:
        ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
        lang = SOURCE_EXTS.get(ext)
        rec = {"path": path, "size": size, "module": module_of(path, mods), "lang": lang or "", "test": is_test_path(path),
               "sset": source_set(path), "data": None, "ext": ext}
        if lang and not is_build_script(path) and size <= MAX_BYTES:
            try:
                mt = (root / path).stat().st_mtime_ns
            except OSError:
                mt = 0
            c = cache.get(path)
            if c and c.get("m") == [size, mt] and c.get("d") is not None:
                rec["data"] = c["d"]
                new_cache[path] = c
            else:
                todo.append((path, str(root / path), lang, mt, size))
        recs.append(rec)
    by_path = {r["path"]: r for r in recs}
    parsed = 0
    if todo:
        tasks = [(t[0], t[1], t[2]) for t in todo]
        workers = cfg.get("workers") or min(8, os.cpu_count() or 1)
        results = None
        ticker = ProgressTicker("Parseando arquivos", len(tasks), quiet=quiet)
        if len(tasks) > 150 and workers > 1:
            try:
                with ProcessPoolExecutor(max_workers=workers) as ex:
                    results = []
                    for fut in as_completed({ex.submit(parse_task, t): t for t in tasks}):
                        results.append(fut.result())
                        ticker.tick(len(results))
            except Exception:  # noqa: BLE001 - ambientes sem fork/spawn: cai para sequencial
                results = None
        if results is None:
            results = []
            for t in tasks:
                results.append(parse_task(t))
                ticker.tick(len(results))
        ticker.done()
        meta = {t[0]: (t[3], t[4]) for t in todo}
        for rel, sha, data in results:
            if data is None:
                continue
            by_path[rel]["data"] = data
            mt, sz = meta[rel]
            new_cache[rel] = {"m": [sz, mt], "h": sha, "d": data}
            parsed += 1
    changed_cache = bool(todo) or set(new_cache) != set(cache)
    return {"root": root, "cfg": cfg, "files": recs, "mods": mods, "proj": proj, "parsed": parsed,
            "cached": sum(1 for r in recs if r["data"] is not None) - parsed, "cache_out": new_cache if changed_cache else None,
            "secs": time.time() - t0}


# =========================================================================== #
# Grafo: simbolos globais, resolucao de nomes, arestas
# =========================================================================== #
TYPE_KINDS = {"class", "interface", "object", "enum", "annotation", "data class", "value class", "companion",
              "abstract class", "typealias"}
CLASSLIKE = TYPE_KINDS - {"interface", "typealias", "annotation"}
STRONG = ("extends", "implements", "injects")
CALL_KINDS = ("calls", "instantiates")
FOLLOW_KINDS = ("calls", "instantiates", "implemented_by")
DEP_KINDS = ("calls", "instantiates", "uses", "injects", "extends", "implements", "overrides", "reads", "writes", "throws", "references", "consumes_from")
ACCESS_KINDS = ("reads", "writes")
EXCL_DEAD_ANN = {"Deprecated", "Suppress", "JvmStatic", "JvmOverloads", "JvmName", "JvmField", "Test", "ParameterizedTest",
                 "BeforeEach", "AfterEach", "BeforeAll", "AfterAll", "Composable", "Preview", "Override", "PostConstruct",
                 "PreDestroy", "Bean", "Provides", "Binds", "EventListener", "Scheduled", "OptIn", "InternalApi", "PublishedApi"}
EXCL_DEAD_NAMES = {"main", "toString", "equals", "hashCode", "invoke", "compareTo", "iterator", "component1", "component2",
                   "component3", "getValue", "setValue", "provideDelegate", "contains", "next", "hasNext", "close", "run", "call"}
MAP_ANN = {"GetMapping": "GET", "PostMapping": "POST", "PutMapping": "PUT", "DeleteMapping": "DELETE", "PatchMapping": "PATCH",
           "RequestMapping": "ANY", "GET": "GET", "POST": "POST", "PUT": "PUT", "DELETE": "DELETE", "PATCH": "PATCH", "HEAD": "HEAD"}
LISTENER_ANN = {"KafkaListener", "RabbitListener", "JmsListener", "SqsListener", "EventListener", "StreamListener",
                "TransactionalEventListener", "PubSubListener"}
PARAM_ROLE_ANN = {  # Spring e JAX-RS (mesmo conceito, nomes diferentes)
    "PathVariable": "path", "PathParam": "path",
    "RequestParam": "query", "QueryParam": "query",
    "RequestHeader": "header", "HeaderParam": "header",
    "RequestBody": "body",
    "CookieValue": "cookie", "CookieParam": "cookie",
}
AUTH_ANN = {"PreAuthorize", "PostAuthorize", "Secured", "RolesAllowed", "PermitAll", "DenyAll"}


def first_type_name(text: str) -> str:
    m = re.search(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", text or "")
    return m.group() if m else ""


def ann_name(a: str) -> str:
    return a.split("(", 1)[0].removeprefix("ctor:")


def ann_args(a: str) -> str:
    return a[a.index("(") + 1:-1] if "(" in a else ""


def detect_layer(name: str, annots: list, pkg: str, cfg: dict) -> str:
    an = {ann_name(a) for a in annots}
    dotted = "." + pkg + "."
    for lay in cfg.get("layers", []) + [{"name": l, "annotations": sorted(a), "suffixes": list(s), "packages": list(p)} for l, a, s, p in LAYERS]:
        if an & set(lay.get("annotations", [])):
            return lay["name"]
    for lay in cfg.get("layers", []) + [{"name": l, "annotations": sorted(a), "suffixes": list(s), "packages": list(p)} for l, a, s, p in LAYERS]:
        if any(name.endswith(x) and name != x for x in lay.get("suffixes", [])):
            return lay["name"]
    for lay in cfg.get("layers", []) + [{"name": l, "annotations": sorted(a), "suffixes": list(s), "packages": list(p)} for l, a, s, p in LAYERS]:
        if any(x in dotted for x in lay.get("packages", [])):
            return lay["name"]
    return "other"


DEFAULT_ENTRY_INTERFACES = [
    # AWS Lambda handlers -- reconhecidos por padrao (sem exigir config), mesmo tratamento
    # ja dado a HTTP/Kafka/SQS/@Scheduled. Kind "listener": reaproveita a exibicao/agrupamento
    # ja existente (o label "implements RequestHandler" ja deixa claro que e Lambda).
    {"iface": "RequestHandler", "kind": "listener"},
    {"iface": "RequestStreamHandler", "kind": "listener"},
]


def entry_iface_kinds(cfg: dict) -> dict[str, str]:
    """entry_interfaces aceita tanto ["Iface", ...] (retrocompatibilidade, tudo vira kind
    'listener') quanto [{"iface": "Iface", "kind": "..."}] para projetos que precisam
    distinguir papeis (ex.: consumidor vs. produtor de mensageria). DEFAULT_ENTRY_INTERFACES
    sempre entra primeiro; a config do projeto e aditiva (pode sobrescrever o kind de um
    default reaproveitando o mesmo nome de interface)."""
    out: dict[str, str] = {}
    for item in DEFAULT_ENTRY_INTERFACES + cfg.get("entry_interfaces", []):
        if isinstance(item, str):
            out[item] = "listener"
        elif isinstance(item, dict) and item.get("iface"):
            out[item["iface"]] = item.get("kind") or "listener"
    return out


def _reconstruct_pipeline(calls) -> list[str] | None:
    """Reconstroi uma cadeia de operadores reativos (Flow/Reactor) a partir de sym["calls"]
    (lista de (nome, recv, linha) ja populada por extract_refs) — reaproveita a mesma marcacao
    '@call:.<elo anterior>' que o resolvedor de chamadas encadeadas ja usa pra qualquer cadeia
    de metodo (ver Parser._chain_call_name), so filtrando pelo vocabulario reativo. Nao resolve
    tipo do receptor (custaria uma chamada a Graph.var_type() por cadeia); em vez disso exige
    pelo menos um operador do grupo EXCLUSIVO (so existe em Flow/Reactor) pra reportar, o que
    evita o falso positivo mais comum: 'list.map{}.filter{}.first()' sobre uma List comum.
    Simplificacao aceita: se o mesmo nome de operador aparece 2x na cadeia (raro, ex.:
    '.map{}.map{}'), a reconstrucao por nome pode colidir — mesmo espirito de aproximacao
    honesta ja documentado em _try/_classify_unresolved."""
    vocab = REACTIVE_OPS_EXCLUSIVE | REACTIVE_OPS_AMBIGUOUS
    entries = [(nm, recv) for nm, recv, _ in calls if nm in vocab]
    if len(entries) < 2:
        return None
    names = {nm for nm, _ in entries}

    def _linked_name(recv: str) -> str:
        # "@call:<qualificador>.<nome>" -- o qualificador e a expressao anterior da cadeia,
        # so o <nome> final importa aqui (ver Parser._chain_call_name).
        return recv[len("@call:"):].rpartition(".")[-1] if recv.startswith("@call:") else ""

    linked_from: dict[str, str] = {}
    for nm, recv in entries:
        prev = _linked_name(recv)
        if prev in names:
            linked_from[prev] = nm
    roots = [nm for nm, recv in entries if _linked_name(recv) not in names]
    if not roots:
        return None
    chain = [roots[0]]
    seen = {roots[0]}
    while chain[-1] in linked_from and linked_from[chain[-1]] not in seen:
        nxt = linked_from[chain[-1]]
        chain.append(nxt)
        seen.add(nxt)
    if len(chain) < 2 or not (set(chain) & REACTIVE_OPS_EXCLUSIVE):
        return None
    return chain


class Graph:
    def __init__(self, P: dict):
        self.P, self.cfg = P, P["cfg"]
        self.syms: list[dict] = []
        self.files: dict[str, dict] = {}
        self.edges: dict[tuple, list] = {}
        self.types: dict[str, dict] = {}
        self.by_pkg: dict[str, dict] = defaultdict(dict)
        self.by_simple: dict[str, list] = defaultdict(list)
        self.members: dict[str, dict] = defaultdict(lambda: defaultdict(list))
        self.top_funs: dict[tuple, list] = defaultdict(list)
        self.funs_by_name: dict[str, list] = defaultdict(list)
        self.sup: dict[str, list] = defaultdict(list)
        self.subs: dict[str, list] = defaultdict(list)
        self.companion: dict[str, str] = {}
        self.chain: list[list] = []
        self.rt_cache: dict = {}
        self.ext_libs: Counter = Counter()
        self.techs: Counter = Counter()
        self.entries: list[dict] = []
        self.unresolved_calls = self.resolved_calls = 0
        self.unresolved_reasons: Counter = Counter()
        self.edge_extra: dict[tuple, list] = {}

    # ------------------------------------------------------------------ #
    def build(self) -> "Graph":
        self._symbols()
        self._resolve_supers()
        self._edges()
        self._overrides()
        self._imports()
        self._entries()
        return self

    def _symbols(self) -> None:
        cfg = self.cfg
        reactive = set(cfg.get("reactive_wrappers", []))
        for rec in sorted(self.P["files"], key=lambda r: r["path"]):
            d = rec["data"]
            if d is None:
                continue
            fi = {"path": rec["path"], "module": rec["module"], "test": rec["test"], "pkg": d["package"], "loc": d["loc"],
                  "lang": rec["lang"], "imp": {}, "wild": [], "todos": d.get("todos", []), "n_todos": d.get("n_todos", 0),
                  "err": d.get("err", ""), "sset": rec["sset"], "ids": [], "raw_imports": d["imports"]}
            for fq, alias, wild in d["imports"]:
                if wild:
                    fi["wild"].append(fq)
                else:
                    fi["imp"][alias or fq.rsplit(".", 1)[-1]] = fq
            self.files[rec["path"]] = fi
            base = len(self.syms)
            for li, s in enumerate(d["syms"]):
                o = s["owner"]
                gid = base + li
                gowner = base + o if o >= 0 else -1
                is_type = s["kind"] in TYPE_KINDS
                pre = self.syms[gowner]["fqn"] if gowner >= 0 else d["package"]
                fqn = f"{pre}.{s['name']}" if pre else s["name"]
                g = dict(s)
                g.update({"id": gid, "fqn": fqn, "pkg": d["package"], "module": rec["module"], "file": rec["path"], "test": rec["test"],
                          "owner": gowner, "loc": max(1, s["end"] - s["line"] + 1), "is_type": is_type})
                if gowner >= 0:
                    self.chain.append(([fqn] if is_type else []) + self.chain[gowner] if is_type else self.chain[gowner])
                else:
                    self.chain.append([fqn] if is_type else [])
                if is_type:
                    g["layer"] = detect_layer(g["name"], g["annots"], d["package"], cfg)
                elif gowner >= 0:
                    g["layer"] = self.syms[gowner]["layer"]
                else:
                    g["layer"] = detect_layer(Path(rec["path"]).stem, g["annots"], d["package"], cfg)
                if g["kind"] in ("fun", "property"):
                    rt = first_type_name(g.get("ret") or g.get("ptype") or "")
                    if (reactive and rt in reactive) or rt in COROUTINE_TYPES or "suspend" in g.get("mods", ()):
                        g["async"] = True
                if g["kind"] == "fun":
                    ops = sorted({nm for nm, _, _ in g.get("calls", ()) if nm in COROUTINE_BUILDERS}
                                 | (set(g.get("types", ())) & COROUTINE_TYPE_SIGNALS))
                    if ops:
                        g["coroutine_ops"] = ops
                    pipeline = _reconstruct_pipeline(g.get("calls", ()))
                    if pipeline:
                        g["pipeline"] = pipeline
                if rec["test"]:
                    g["layer"] = "test"
                self.syms.append(g)
                fi["ids"].append(gid)
                if is_type:
                    self.types[fqn] = g
                    self.by_simple[g["name"]].append(fqn)
                    if gowner < 0:
                        self.by_pkg[d["package"]][g["name"]] = fqn
                    if g["kind"] == "companion" and gowner >= 0:
                        self.companion[self.syms[gowner]["fqn"]] = fqn
                if gowner >= 0 and self.syms[gowner]["is_type"] and g["kind"] in ("fun", "property", "enum_entry"):
                    self.members[self.syms[gowner]["fqn"]][g["name"]].append(gid)
                if gowner < 0 and g["kind"] in ("fun", "property"):
                    self.top_funs[(d["package"], g["name"])].append(gid)
                if g["kind"] == "fun":
                    self.funs_by_name[g["name"]].append(gid)
        for fi in self.files.values():
            for fq, _, _ in fi["raw_imports"]:
                self.ext_libs[".".join(fq.split(".")[:3])] += 1
                for pref, label in TECH_BY_IMPORT.items():
                    if fq.startswith(pref):
                        self.techs[label] += 1
                        break

    # ------------------------------------------------------------------ #
    def rt(self, raw: str, fi: dict, chain: list):
        key = (fi["path"], chain[0] if chain else "", raw)
        if key in self.rt_cache:
            return self.rt_cache[key]
        r = self._rt(raw, fi, chain)
        self.rt_cache[key] = r
        return r

    def _uniq(self, raw: str, fi: dict):
        c = self.by_simple.get(raw, [])
        if len(c) == 1:
            return c[0], 0.5
        if len(c) > 1:
            same = [x for x in c if self.types[x]["module"] == fi["module"]]
            if len(same) == 1:
                return same[0], 0.5
        return None

    def _rt(self, raw: str, fi: dict, chain: list):
        types = self.types
        if "." in raw:
            if raw in types:
                return raw, 1.0
            head, rest = raw.split(".", 1)
            if head[:1].isupper():
                h = self._rt(head, fi, chain)
                if h:
                    c = h[0] + "." + rest
                    if c in types:
                        return c, h[1]
                return self._uniq(raw.rsplit(".", 1)[-1], fi)
            return None
        for oc in chain:
            c = oc + "." + raw
            if c in types:
                return c, 1.0
        imp = fi["imp"].get(raw)
        if imp:
            return (imp, 1.0) if imp in types else None
        c = self.by_pkg.get(fi["pkg"], {}).get(raw)
        if c:
            return c, 1.0
        for w in fi["wild"]:
            c = w + "." + raw
            if c in types:
                return c, 0.9
        return self._uniq(raw, fi)

    def _resolve_supers(self) -> None:
        for s in self.syms:
            if not s["is_type"]:
                continue
            fi = self.files[s["file"]]
            ch = self.chain[s["id"]][1:] if len(self.chain[s["id"]]) > 1 else []
            s["ext_supers"], s["sup_ids"] = [], []
            for raw in s["supers"]:
                r = self.rt(raw, fi, ch)
                if r and r[0] in self.types and r[0] != s["fqn"]:
                    self.sup[s["fqn"]].append(r[0])
                    self.subs[r[0]].append(s["fqn"])
                    s["sup_ids"].append(self.types[r[0]]["id"])
                else:
                    s["ext_supers"].append(raw.rsplit(".", 1)[-1])

    def add_edge(self, src: int, dst: int, kind: str, line: int, conf: float) -> None:
        """Uma aresta por (src, dst, kind); so a 1a linha vira 'l' (formato usado em todo
        lugar que le G.edges), mas ocorrencias extras nao se perdem: ficam em edge_extra,
        capadas, para quem precisar de evidencia completa (ver emit_store)."""
        if src == dst:
            return
        k = (src, dst, kind)
        e = self.edges.get(k)
        if e is None:
            self.edges[k] = [line, conf]
            return
        if conf > e[1]:
            e[1] = conf
        if line != e[0]:
            extra = self.edge_extra.setdefault(k, [])
            if line not in extra and len(extra) < 5:
                extra.append(line)

    def find_member(self, tfqn: str, name: str, want_fun: bool = True) -> list:
        seen, q = set(), deque([tfqn])
        while q:
            t = q.popleft()
            if t in seen:
                continue
            seen.add(t)
            hits = self.members.get(t, {}).get(name)
            if hits:
                f = [h for h in hits if self.syms[h]["kind"] == "fun"] if want_fun else hits
                if f:
                    return f[:3]
            comp = self.companion.get(t)
            if comp and comp not in seen:
                q.append(comp)
            q.extend(self.sup.get(t, []))
        return []

    def var_type(self, s: dict, recv: str, fi: dict, depth: int = 0) -> str:
        t = s["locals"].get(recv)
        if t and t.startswith("@call:") and depth < 3:
            inner, _, meth = t[6:].rpartition(".")
            ids, kind, conf = self.resolve_call(s, meth, inner, fi, depth + 1)
            for i in ids:
                ret = first_type_name(self.syms[i]["ret"] or self.syms[i]["ptype"])
                if ret:
                    return ret
            return ""
        if t:
            return t
        for pn, pt, *_ in s["params"]:
            if pn == recv:
                return first_type_name(pt)
        for tf in self.chain[s["id"]]:
            for h in self.members.get(tf, {}).get(recv, []):
                if self.syms[h]["kind"] == "property" and self.syms[h].get("ptype"):
                    return first_type_name(self.syms[h]["ptype"])
        return ""

    def ext_funs(self, name: str, tname: str) -> list:
        simple = tname.rsplit(".", 1)[-1]
        return [i for i in self.funs_by_name.get(name, []) if self.syms[i]["recv"] and first_type_name(self.syms[i]["recv"]).rsplit(".", 1)[-1] == simple][:3]

    def fallback(self, s: dict, name: str) -> list:
        if name in COMMON_NAMES:
            return []
        c = [i for i in self.funs_by_name.get(name, []) if (self.syms[i]["vis"] != "private" or self.syms[i]["file"] == s["file"])
             and (s["test"] or not self.syms[i]["test"])]
        return c if len(c) == 1 else []

    def _classify_unresolved(self, s: dict, name: str, recv: str, fi: dict) -> str:
        """Raio-x agregado (nao cirurgico) de por que uma chamada ficou sem resolver: nome
        generico demais pra arriscar (fallback recusa de proposito), receptor que o parser nao
        conseguiu determinar, receptor que aponta pra fora do projeto (tipo/retorno externo —
        cobre tanto 'Tipo.metodo()'/cadeias quanto 'variavel.metodo()' quando o tipo da
        variavel e resolvivel mas nao e um tipo do projeto, ex.: 'payload: JsonNode',
        'log: KLogger'), nome com mais de um candidato (fallback tambem recusa) ou, por
        ultimo, nome que nao bate com nada (inclui chamadas de topo tipo 'setOf(...)': sem
        base de dados da stdlib, nao da pra distinguir 'e da stdlib' de 'e erro de digitacao')."""
        if name in COMMON_NAMES:
            return "nome_generico"
        if recv == "?":
            return "receptor_incerto"
        if recv[:1].isupper() or recv.startswith("@call:") or recv.startswith("@lambda:"):
            return "tipo_ou_retorno_externo"
        if recv and recv not in ("this", "super"):
            tname = self.var_type(s, recv, fi)
            if tname:
                r = self.rt(tname, fi, self.chain[s["id"]])
                if not (r and r[0] in self.types):
                    return "tipo_ou_retorno_externo"
        if len(self.funs_by_name.get(name, [])) > 1:
            return "ambiguo"
        return "nao_encontrado"

    def resolve_call(self, s: dict, name: str, recv: str, fi: dict, depth: int = 0):
        """-> (lista de ids, tipo_aresta, confianca)."""
        ch = self.chain[s["id"]]
        if name[:1].isupper():
            r = self.rt(name, fi, ch)
            if r and r[0] in self.types:
                return [self.types[r[0]]["id"]], "instantiates", 0.9 * r[1] if r[1] < 1 else 0.95
        if recv.startswith("@call:"):
            if depth >= 3:
                return self.fallback(s, name), "calls", 0.4
            inner, _, meth = recv[6:].rpartition(".")
            ids, _, _ = self.resolve_call(s, meth, inner, fi, depth + 1)
            for i in ids:
                # construtor (NestedHelper().help()): o "retorno" da chamada e o proprio tipo
                rt_name = (self.syms[i]["fqn"] if self.syms[i].get("is_type")
                           else first_type_name(self.syms[i]["ret"] or self.syms[i]["ptype"]))
                if not rt_name:
                    continue
                r = self.rt(rt_name, fi, ch)
                if r and r[0] in self.types:
                    h = self.find_member(r[0], name)
                    if h:
                        return h, "calls", 0.75
                ex = self.ext_funs(name, rt_name)
                if ex:
                    return ex, "calls", 0.55
            return self.fallback(s, name), "calls", 0.4
        if recv.startswith("@lambda:"):
            return self._resolve_lambda_recv(s, name, recv, fi, depth)
        if recv == "":
            return self._resolve_unqualified(s, name, fi, ch)
        if recv in ("this", "super"):
            for tf in ch[:1]:
                base = self.sup.get(tf, []) if recv == "super" else [tf]
                for b in base:
                    h = self.find_member(b, name)
                    if h:
                        return h, "calls", 0.9
            return [], "calls", 0
        if recv == "?":
            return self.fallback(s, name), "calls", 0.4
        if recv[:1].isupper():
            r = self.rt(recv, fi, ch)
            if r and r[0] in self.types:
                h = self.find_member(r[0], name)
                return (h, "calls", 0.9) if h else ([], "calls", 0)
            return [], "calls", 0
        tname = self.var_type(s, recv, fi, depth)
        if tname:
            r = self.rt(tname, fi, ch)
            if r and r[0] in self.types:
                h = self.find_member(r[0], name) or self.ext_funs(name, tname)
                if h:
                    return h, "calls", 0.85
                return [], "calls", 0
            ex = self.ext_funs(name, tname)
            return (ex, "calls", 0.6) if ex else ([], "calls", 0)
        return self.fallback(s, name), "calls", 0.4

    def _resolve_unqualified(self, s: dict, name: str, fi: dict, ch: list):
        """Chamada sem receiver explicito (nome() dentro do proprio escopo): membro do proprio
        tipo/outer, funcao de topo no mesmo pacote, import direto, import com wildcard ou,
        por ultimo, candidato unico global."""
        for tf in ch:
            h = self.find_member(tf, name)
            if h:
                return h, "calls", 0.9
        if (fi["pkg"], name) in self.top_funs:
            return [i for i in self.top_funs[(fi["pkg"], name)] if self.syms[i]["kind"] == "fun"][:3], "calls", 0.9
        imp = fi["imp"].get(name)
        if imp and "." in imp:
            pk = imp.rsplit(".", 1)[0]
            h = [i for i in self.top_funs.get((pk, name), []) if self.syms[i]["kind"] == "fun"]
            if h:
                return h[:3], "calls", 1.0
        for w in fi["wild"]:
            h = [i for i in self.top_funs.get((w, name), []) if self.syms[i]["kind"] == "fun"]
            if h:
                return h[:3], "calls", 0.9
        return self.fallback(s, name), "calls", 0.4

    def _resolve_lambda_recv(self, s: dict, name: str, recv: str, fi: dict, depth: int):
        """Chamada sem receiver dentro do corpo (bare) de um lambda trailing 'nome { ... }':
        se a chamada externa resolve para uma funcao cujo ultimo parametro e do tipo
        'Tipo.(...) -> Y' (lambda com receiver, ex.: DSL builders), tenta achar 'name' como
        membro de 'Tipo' antes de cair no tratamento normal de chamada sem receiver (como se
        o lambda nao tivesse receiver implicito nenhum)."""
        ch = self.chain[s["id"]]
        idx_txt = recv[8:]
        idx = int(idx_txt) if idx_txt.isdigit() else -1
        calls = s.get("calls") or []
        if depth < 3 and 0 <= idx < len(calls):
            outer_name, outer_recv, _ = calls[idx]
            ids, _, _ = self.resolve_call(s, outer_name, outer_recv, fi, depth + 1)
            for i in ids:
                params = self.syms[i].get("params") or []
                if not params:
                    continue
                m = _LAMBDA_RECV.match(params[-1][1] or "")
                if not m:
                    continue
                r = self.rt(m.group(1), fi, ch)
                if r and r[0] in self.types:
                    h = self.find_member(r[0], name)
                    if h:
                        return h, "calls", 0.7
        return self._resolve_unqualified(s, name, fi, ch)

    def _edges(self) -> None:
        for s in self.syms:
            fi = self.files[s["file"]]
            ch = self.chain[s["id"]]
            tch = ch[1:] if s["is_type"] else ch
            sid = s["id"]
            if s["is_type"]:
                for raw in s["supers"]:
                    r = self.rt(raw, fi, tch)
                    if r and r[0] in self.types:
                        t = self.types[r[0]]
                        kind = "implements" if t["kind"] == "interface" else ("extends" if (t["kind"] in CLASSLIKE or raw in s["super_calls"]) else "implements")
                        self.add_edge(sid, t["id"], kind, s["line"], r[1])
                for raw in s["inject"]:
                    r = self.rt(raw, fi, tch)
                    if r and r[0] in self.types:
                        self.add_edge(sid, self.types[r[0]]["id"], "injects", s["line"], r[1])
            for raw in s["types"]:
                r = self.rt(raw, fi, tch)
                if r and r[0] in self.types:
                    t = self.types[r[0]]
                    if not any((sid, t["id"], k) in self.edges for k in STRONG):
                        self.add_edge(sid, t["id"], "uses", s["line"], r[1])
            for fname, recv, line, mode in s["fields"]:
                ids = self.resolve_field(s, fname, recv, fi)
                for i in ids:
                    self.add_edge(sid, i, "writes" if mode == "w" else "reads", line, 0.8)
            for raw, line in s["throws"]:
                r = self.rt(raw, fi, tch)
                if r and r[0] in self.types:
                    self.add_edge(sid, self.types[r[0]]["id"], "throws", line, r[1])
            for raw, line in s["catches"]:
                r = self.rt(raw, fi, tch)
                if r and r[0] in self.types:
                    self.add_edge(sid, self.types[r[0]]["id"], "catches", line, r[1])
            for name, recv, line in s["calls"]:
                ids, kind, conf = self.resolve_call(s, name, recv, fi)
                if ids and conf >= self.cfg["min_call_conf"] - 1e-9:
                    self.resolved_calls += 1
                    for i in ids:
                        self.add_edge(sid, i, kind, line, conf)
                else:
                    self.unresolved_calls += 1
                    self.unresolved_reasons[self._classify_unresolved(s, name, recv, fi)] += 1

    def resolve_field(self, s: dict, name: str, recv: str, fi: dict) -> list:
        """Resolve acesso a propriedade de um objeto (obj.campo)."""
        ch = self.chain[s["id"]]
        if recv.startswith("@call:"):
            inner, _, meth = recv[6:].rpartition(".")
            ids, _, _ = self.resolve_call(s, meth, inner, fi, 1)
            for i in ids:
                rt_name = (self.syms[i]["fqn"] if self.syms[i].get("is_type")
                           else first_type_name(self.syms[i]["ret"] or self.syms[i]["ptype"]))
                if not rt_name:
                    continue
                r = self.rt(rt_name, fi, ch)
                if r and r[0] in self.types:
                    hits = [h for h in self.find_member(r[0], name, want_fun=False)
                            if self.syms[h]["kind"] in ("property", "enum_entry")]
                    if hits:
                        return hits[:2]
            return []
        if recv in ("this", "?"):
            for tf in ch:
                hits = [h for h in self.members.get(tf, {}).get(name, []) if self.syms[h]["kind"] in ("property", "enum_entry")]
                if hits:
                    return hits[:2]
            return []
        if recv[:1].isupper():
            r = self.rt(recv, fi, ch)
            if r and r[0] in self.types:
                hits = self.find_member(r[0], name, want_fun=False)
                return [h for h in hits if self.syms[h]["kind"] in ("property", "enum_entry")][:2]
            return []
        tname = self.var_type(s, recv, fi)
        if not tname or tname.startswith("@call:"):
            return []
        r = self.rt(tname, fi, ch)
        if r and r[0] in self.types:
            hits = self.find_member(r[0], name, want_fun=False)
            return [h for h in hits if self.syms[h]["kind"] in ("property", "enum_entry")][:2]
        return []

    def _overrides(self) -> None:
        for s in self.syms:
            if s["kind"] != "fun" or s["owner"] < 0:
                continue
            if "override" not in s["mods"] and not any(ann_name(a) == "Override" for a in s["annots"]):
                continue
            owner = self.syms[s["owner"]]
            if not owner["is_type"]:
                continue
            seen, q = set(), deque(self.sup.get(owner["fqn"], []))
            while q:
                t = q.popleft()
                if t in seen:
                    continue
                seen.add(t)
                hit = [h for h in self.members.get(t, {}).get(s["name"], []) if self.syms[h]["kind"] == "fun"
                       and len(self.syms[h]["params"]) == len(s["params"])]
                if hit:
                    for h in hit[:2]:
                        self.add_edge(s["id"], h, "overrides", s["line"], 1.0)
                else:
                    q.extend(self.sup.get(t, []))

    def _imports(self) -> None:
        self.file_edges: Counter = Counter()
        for path, fi in self.files.items():
            for fq, alias, wild in fi["raw_imports"]:
                dst = None
                if fq in self.types:
                    dst = self.types[fq]["file"]
                elif not wild and "." in fq:
                    pk = fq.rsplit(".", 1)
                    h = self.top_funs.get((pk[0], pk[1]))
                    if h:
                        dst = self.syms[h[0]]["file"]
                if dst and dst != path:
                    self.file_edges[(path, dst)] += 1
        for (src, dst, kind), _ in self.edges.items():
            a, b = self.syms[src]["file"], self.syms[dst]["file"]
            if a != b and kind in DEP_KINDS:
                self.file_edges[(a, b)] += 1

    def tfin_get(self, i: int) -> set:
        return getattr(self, "_tfin", {}).get(i, set())

    # ------------------------------------------------------------------ #
    def _entries(self) -> None:
        cfg = self.cfg
        extra = set(cfg.get("entry_annotations", []))
        iface_kinds = entry_iface_kinds(cfg)
        ifaces = set(iface_kinds)
        E = self.entries
        prefix: dict[int, str] = {}
        class_auth: dict[int, str] = {}
        iface_types = {s["id"] for s in self.syms if s["is_type"] and ifaces & set(s.get("ext_supers", []))} if ifaces else set()
        for s in self.syms:
            if s["is_type"]:
                for a in s["annots"]:
                    if ann_name(a) in ("RequestMapping", "Path"):
                        m = re.search(r'"([^"]*)"', a)
                        prefix[s["id"]] = m.group(1) if m else ""
                    if ann_name(a) == "SpringBootApplication":
                        E.append({"kind": "app", "label": "SpringBootApplication", "sym": s["id"]})
                    if ann_name(a) in AUTH_ANN:
                        class_auth[s["id"]] = a
        ktor_files = {p for p, fi in self.files.items() if any(i[0].startswith("io.ktor") for i in fi["raw_imports"])}
        for s in self.syms:
            if s["test"]:
                continue
            if s["kind"] == "fun":
                if s["name"] == "main" and (s["owner"] < 0 or any(ann_name(a) == "JvmStatic" for a in s["annots"])):
                    E.append({"kind": "main", "label": "main()", "sym": s["id"]})
                for a in s["annots"]:
                    an = ann_name(a)
                    if an in MAP_ANN:
                        args = ann_args(a)
                        paths = re.findall(r'"([^"]*)"', args) or [""]
                        meth = MAP_ANN[an]
                        if an == "RequestMapping":
                            mm = re.findall(r"RequestMethod\.(\w+)", args)
                            meth = "/".join(mm) if mm else "ANY"
                        pre = prefix.get(s["owner"], "")
                        roles: dict[str, list] = {"path": [], "query": [], "header": [], "cookie": []}
                        request = None
                        for pparam in s["params"]:
                            pname, ptype = pparam[0], pparam[1]
                            pannots = pparam[2] if len(pparam) > 2 else []
                            role = next((PARAM_ROLE_ANN[ann_name_lite(pa)] for pa in pannots
                                         if ann_name_lite(pa) in PARAM_ROLE_ANN), None)
                            if role == "body":
                                request = ptype
                            elif role:
                                roles[role].append(pname)
                        status = None
                        auth = None
                        for a2 in s["annots"]:
                            an2 = ann_name(a2)
                            if an2 == "ResponseStatus" and status is None:
                                m2 = re.search(r"HttpStatus\.(\w+)", ann_args(a2))
                                status = m2.group(1) if m2 else (ann_args(a2) or None)
                            elif an2 in AUTH_ANN and auth is None:
                                auth = a2
                        auth = auth or class_auth.get(s["owner"])
                        for p in paths[:3]:
                            full = ("/" + (pre.strip("/") + "/" + p.strip("/")).strip("/")).replace("//", "/")
                            E.append({"kind": "http", "label": f"{meth} {full}", "sym": s["id"],
                                      "request": request, "response": s["ret"] or None,
                                      "params": {k: v for k, v in roles.items() if v},
                                      "status": status, "auth": auth})
                    elif an in LISTENER_ANN:
                        E.append({"kind": "listener", "label": f"@{an}({ann_args(a)[:80]})", "sym": s["id"]})
                    elif an == "Scheduled":
                        E.append({"kind": "schedule", "label": f"@Scheduled({ann_args(a)[:60]})", "sym": s["id"]})
                    elif an in extra:
                        E.append({"kind": "custom", "label": f"@{an}", "sym": s["id"]})
                if s["owner"] in iface_types and "override" in s["mods"]:
                    iface = next(iter(ifaces & set(self.syms[s["owner"]].get("ext_supers", []))))
                    E.append({"kind": iface_kinds[iface], "label": f"implements {iface}", "sym": s["id"]})
            if s["routes"] and s["file"] in ktor_files:
                for verb, path, _ in s["routes"]:
                    E.append({"kind": "http", "label": f"{verb} {path}", "sym": s["id"]})
        for e in E:
            e["file"], e["line"] = self.syms[e["sym"]]["file"], self.syms[e["sym"]]["line"]
        E.sort(key=lambda e: (e["kind"] != "http", e["kind"], e["label"], e["file"], e["line"]))


# =========================================================================== #
# Analises
# =========================================================================== #
def sccs(nodes, adj) -> list[list]:
    index, low, onst, stack, res, idx = {}, {}, set(), [], [], 0
    for v0 in nodes:
        if v0 in index:
            continue
        index[v0] = low[v0] = idx
        idx += 1
        stack.append(v0)
        onst.add(v0)
        work = [(v0, iter(sorted(adj.get(v0, ()))))]
        while work:
            v, it = work[-1]
            adv = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = idx
                    idx += 1
                    stack.append(w)
                    onst.add(w)
                    work.append((w, iter(sorted(adj.get(w, ())))))
                    adv = True
                    break
                if w in onst:
                    low[v] = min(low[v], index[w])
            if adv:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    onst.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    res.append(sorted(comp))
    return sorted(res, key=lambda c: (-len(c), c))


def type_of(G: Graph, i: int) -> int:
    while i >= 0 and not G.syms[i]["is_type"]:
        i = G.syms[i]["owner"]
    return i


def analyze(G: Graph) -> dict:
    cfg, S = G.cfg, G.syms
    A: dict = {}
    P = G.P
    mods = P["mods"]
    idmap = {m["id"]: d for d, m in mods.items()}
    # --- adjacencias ---
    fadj, padj, madj = defaultdict(set), defaultdict(set), defaultdict(set)
    pcount, mcount = Counter(), Counter()
    for (a, b), n in G.file_edges.items():
        fa, fb = G.files[a], G.files[b]
        if fa["test"] or fb["test"]:
            continue
        fadj[a].add(b)
        if fa["pkg"] != fb["pkg"]:
            padj[fa["pkg"]].add(fb["pkg"])
            pcount[(fa["pkg"], fb["pkg"])] += n
        if fa["module"] != fb["module"]:
            ida, idb = mods[fa["module"]]["id"], mods[fb["module"]]["id"]
            madj[ida].add(idb)
            mcount[(ida, idb)] += n
    A["pcount"], A["mcount"] = pcount, mcount
    decl = {m["id"]: set(m["deps"]) for m in mods.values()}
    A["cycles_modules"] = sccs(sorted(decl), decl)
    A["cycles_packages"] = sccs(sorted(padj), padj)[:15]
    A["cycles_files"] = sccs(sorted(fadj), fadj)[:10]
    # --- deps declaradas vs uso real ---
    def closure(m):
        seen, st = set(), list(decl.get(m, ()))
        while st:
            x = st.pop()
            if x not in seen:
                seen.add(x)
                st += list(decl.get(x, ()))
        return seen
    und, unused = [], []
    for a, targets in madj.items():
        cl = closure(a)
        for b in sorted(targets):
            if b not in cl:
                und.append((a, b, mcount[(a, b)]))
    for a, ds in decl.items():
        for b in sorted(ds):
            if b not in madj.get(a, ()) and mods[idmap[b]]["kind"] != "dir":
                unused.append((a, b))
    A["undeclared"], A["unused"] = und, unused
    # --- fan-in / fan-out de tipos e, por baixo, de cada simbolo individual ---
    fin, fout = defaultdict(set), defaultdict(set)
    indeg, outdeg = Counter(), Counter()
    for (src, dst, kind), _ in G.edges.items():
        if kind not in DEP_KINDS:
            continue
        indeg[dst] += 1
        outdeg[src] += 1
        ta, tb = type_of(G, src), type_of(G, dst)
        if ta >= 0 and tb >= 0 and ta != tb:
            fout[ta].add(tb)
            fin[tb].add(ta)
    A["fan_in"] = sorted(((len(v), k) for k, v in fin.items() if not S[k]["test"]), reverse=True)[:15]
    A["fan_out"] = sorted(((len(v), k) for k, v in fout.items() if not S[k]["test"]), reverse=True)[:15]
    A["tfin"], A["tfout"] = fin, fout
    A["sym_fan_in"], A["sym_fan_out"] = indeg, outdeg
    G._tfin = fin
    # --- god classes, complexidade ---
    members_n = Counter(s["owner"] for s in S if s["owner"] >= 0 and s["kind"] in ("fun", "property"))
    type_loc = {s["id"]: s["loc"] for s in S if s["is_type"]}
    A["god"] = sorted(((type_loc[i], members_n[i], i) for i in type_loc
                       if not S[i]["test"] and S[i]["kind"] not in ("typealias", "enum", "interface", "annotation")
                       and (type_loc[i] >= cfg["god_class_loc"] or members_n[i] >= cfg["god_class_members"])), reverse=True)[:20]
    funs = [s for s in S if s["kind"] in ("fun", "constructor") and not s["test"]]
    A["complex"] = sorted(((s["cc"], s["id"]) for s in funs if s["cc"] >= cfg["cc_threshold"]), reverse=True)[:25]
    A["long_funs"] = sorted(((s["loc"], s["id"]) for s in funs if s["loc"] >= cfg["long_fun_loc"]), reverse=True)[:15]
    A["many_params"] = sorted(((len(s["params"]), s["id"]) for s in funs if len(s["params"]) >= cfg["many_params"]), reverse=True)[:15]
    # --- codigo morto (candidatos) ---
    entry_ids = {e["sym"] for e in G.entries}
    ann_children = {s["owner"] for s in S if s["owner"] >= 0 and s["annots"]}
    ign = EXCL_DEAD_ANN | set(cfg.get("dead_ignore_annotations", []))
    dead = []
    for s in S:
        if s["test"] or s["vis"] == "private" or s["kind"] not in ("class", "interface", "object", "fun", "data class", "enum", "abstract class", "value class"):
            continue
        if s["id"] in entry_ids or s["name"] in EXCL_DEAD_NAMES or "override" in s["mods"] or "operator" in s["mods"]:
            continue
        if s["is_type"] and (s["id"] in ann_children or G.sup.get(s["fqn"]) or s.get("ext_supers")):
            continue
        if s["owner"] >= 0 and indeg[s["owner"]]:
            continue
        if any(ann_name(a) in ign for a in s["annots"]) or (s["annots"] and s["is_type"]):
            continue
        if s["owner"] >= 0 and S[s["owner"]]["annots"] and S[s["owner"]]["kind"] != "companion" and S[s["owner"]]["layer"] in ("controller", "job", "config"):
            continue
        if s["owner"] >= 0 and S[s["owner"]]["kind"] == "interface" and not s["ptype"] and s["kind"] == "fun":
            continue
        if indeg[s["id"]] == 0 and (s["kind"] != "fun" or s["owner"] < 0 or not (s["ret"] or s["params"] or True)):
            if s["is_type"] and any(ch["owner"] == s["id"] and indeg[ch["id"]] for ch in ()):
                continue
            if s["is_type"] and s["fqn"] in G.subs:
                continue
            dead.append(s)
    # tipos referenciados apenas por membros proprios nao contam
    A["dead"] = sorted(((s["loc"], s["id"]) for s in dead), reverse=True)[:cfg["max_dead"]]
    A["dead_total"] = len(dead)
    # --- violacoes de camada ---
    forbid = {tuple(x) for x in cfg["forbid"]}
    viol: dict[tuple, dict] = {}
    for (src, dst, kind), (line, conf) in G.edges.items():
        if kind not in DEP_KINDS or kind == "overrides" or conf < 0.8:
            continue
        ta, tb = type_of(G, src), type_of(G, dst)
        if ta < 0 or tb < 0 or ta == tb or S[ta]["test"]:
            continue
        pair = (S[ta]["layer"], S[tb]["layer"])
        if pair in forbid:
            v = viol.setdefault((ta, tb), {"pair": pair, "kinds": set(), "line": line})
            v["kinds"].add(kind)
    A["violations"] = sorted(((S[a]["fqn"], S[b]["fqn"], v["pair"], sorted(v["kinds"]), S[a]["file"], v["line"]) for (a, b), v in viol.items()))
    # --- nomes duplicados ---
    A["dupes"] = sorted(((k, v) for k, v in G.by_simple.items() if len(v) > 1 and not all(G.types[x]["test"] for x in v)),
                        key=lambda kv: (-len(kv[1]), kv[0]))[:15]
    # --- stats ---
    A["kinds"] = Counter(s["kind"] for s in S if not s["test"])
    A["layers"] = Counter(s["layer"] for s in S if s["is_type"] and not s["test"])
    return A


def flows(G: Graph, A: dict) -> list[tuple[dict, list[str]]]:
    cfg, S = G.cfg, G.syms
    adj = defaultdict(list)
    impls = defaultdict(list)
    for (src, dst, kind), (line, conf) in sorted(G.edges.items()):
        if kind in CALL_KINDS and conf >= 0.6:
            adj[src].append((dst, kind, conf))
        elif kind == "overrides":
            impls[dst].append(src)

    def label(i: int) -> str:
        s = S[i]
        if s["kind"] == "constructor" or s["is_type"]:
            return f"{s['name']}()" if s["is_type"] else f"{s['name']}.<init>"
        o = S[s["owner"]]["name"] + "." if s["owner"] >= 0 and S[s["owner"]]["is_type"] else ""
        tag = f" [{S[i]['layer']}]" if S[i]["layer"] not in ("other", "test") and (s["owner"] < 0 or True) else ""
        async_tag = " ⟳" if s.get("async") else ""
        return f"{o}{s['name']}{tag}{async_tag}"

    out = []
    seen_entry = set()
    order = [e for e in G.entries if e["kind"] in ("http", "listener", "schedule", "main", "custom") and not S[e["sym"]]["test"]]
    for e in order[:cfg["max_flows"] * 2]:
        if (e["sym"], e["label"]) in seen_entry:
            continue
        seen_entry.add((e["sym"], e["label"]))
        lines: list[str] = []
        visited = {e["sym"]}

        def walk(i: int, depth: int, ind: str) -> None:
            if len(lines) > 70:
                return
            kids = []
            for dst, kind, conf in adj.get(i, []):
                if S[dst]["is_type"] and kind == "instantiates":
                    continue
                kids.append((dst, kind, conf))
            for m in impls.get(i, []):
                kids.append((m, "impl", 1.0))
            for dst, kind, conf in kids[:cfg["flow_fanout"]]:
                mark = "?" if conf < 0.7 else ""
                pre = "~> " if kind == "impl" else "-> "
                if dst in visited:
                    lines.append(f"{ind}{pre}{label(dst)}{mark} (ja visto)")
                    continue
                visited.add(dst)
                lines.append(f"{ind}{pre}{label(dst)}{mark}  `{S[dst]['file']}:{S[dst]['line']}`")
                if depth + 1 < cfg["flow_depth"]:
                    walk(dst, depth + 1, ind + "  ")

        walk(e["sym"], 0, "  ")
        if lines:
            out.append((e, lines))
        if len(out) >= cfg["max_flows"]:
            break
    return out


# =========================================================================== #
# Store em arquivos (sem banco): JSONL + JSON + Markdown
# =========================================================================== #
SYM_FIELDS = ("id", "fqn", "name", "kind", "layer", "vis", "mods", "annots", "sig", "params", "ret", "recv", "is_type",
              "ptype", "doc", "file", "line", "end", "loc", "cc", "module", "pkg", "owner", "test",
              "supers_fq", "ext_supers", "tparams", "async", "coroutine_ops", "flow", "pipeline")


def sym_record(G: "Graph", s: dict, fan_in: dict | None = None, fan_out: dict | None = None) -> dict:
    r = {k: s.get(k) for k in SYM_FIELDS if k not in ("supers_fq",)}
    r["supers_fq"] = sorted(G.sup.get(s["fqn"], [])) if s["is_type"] else []
    r["owner_fqn"] = G.syms[s["owner"]]["fqn"] if s["owner"] >= 0 else ""
    if fan_in:
        r["fan_in"] = fan_in.get(s["id"], 0)
    if fan_out:
        r["fan_out"] = fan_out.get(s["id"], 0)
    return {k: v for k, v in r.items() if v not in ("", [], 0, None) or k in ("id", "line", "name", "kind", "fqn")}


def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def write_jsonl(w: "Writer", rel: str, rows) -> None:
    w.write(rel, "".join(jdump(r) + "\n" for r in rows))


def emit_store(G: "Graph", A: dict, w: "Writer", D: dict | None = None) -> dict:
    """Escreve o indice legivel por maquina. Retorna o manifesto."""
    P, cfg, S = G.P, G.cfg, G.syms
    sd = cfg["state_dir"]
    fan_in, fan_out = A.get("sym_fan_in"), A.get("sym_fan_out")
    write_jsonl(w, f"{sd}/symbols.jsonl", (sym_record(G, s, fan_in, fan_out) for s in S))
    rows = []
    for key, (ln, c) in sorted(G.edges.items()):
        a, b, k = key
        row = {"s": a, "d": b, "k": k, "l": ln, "c": round(c, 2)}
        extra = G.edge_extra.get(key)
        if extra:
            row["n"] = 1 + len(extra)
            row["lines"] = extra
        rows.append(row)
    rows += [{"s": b, "d": a, "k": "implemented_by", "l": S[a]["line"], "c": round(c, 2)}
             for (a, b, k), (ln, c) in sorted(G.edges.items()) if k == "overrides"]
    write_jsonl(w, f"{sd}/edges.jsonl", rows)
    write_jsonl(w, f"{sd}/files.jsonl", (
        {"path": p, "module": G.P["mods"][f["module"]]["id"], "dir": f["module"], "pkg": f["pkg"], "loc": f["loc"],
         "lang": f["lang"], "test": f["test"], "sset": f["sset"], "syms": len(f["ids"]),
         "imports": [i[0] for i in f["raw_imports"]], "todos": f["todos"], "err": f["err"]}
        for p, f in sorted(G.files.items())))
    others = [r for r in P["files"] if r["data"] is None]
    write_jsonl(w, f"{sd}/assets.jsonl", (
        {"path": r["path"], "module": P["mods"][r["module"]]["id"], "size": r["size"], "ext": r["ext"],
         "kind": asset_kind(r["path"], r["ext"]), "info": asset_info(P["root"], r["path"], r["ext"])}
        for r in sorted(others, key=lambda r: r["path"])))
    mods = [{"id": m["id"], "dir": d, "kind": m["kind"], "build": m["build"], "deps": sorted(m["deps"]),
             "deps_test": sorted(m["deps_t"]), "libs": sorted(m["ext"])[:120], "libs_test": sorted(m["ext_t"])[:60],
             "plugins": sorted(m["plugins"]), **module_stats(G, d)}
            for d, m in sorted(P["mods"].items())]
    write_jsonl(w, f"{sd}/modules.jsonl", mods)
    write_jsonl(w, f"{sd}/entrypoints.jsonl", (
        {"kind": e["kind"], "label": e["label"], "sym": e["sym"], "fqn": S[e["sym"]]["fqn"],
         "file": e["file"], "line": e["line"], "module": P["mods"][S[e["sym"]]["module"]]["id"],
         **({"request": e["request"]} if e.get("request") else {}),
         **({"response": e["response"]} if e.get("response") else {}),
         **({"params": e["params"]} if e.get("params") else {}),
         **({"status": e["status"]} if e.get("status") else {}),
         **({"auth": e["auth"]} if e.get("auth") else {})} for e in G.entries))
    man = manifest(G, A, mods, D)
    w.write(f"{sd}/manifest.json", json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return man


def module_stats(G: "Graph", d: str) -> dict:
    files = [f for f in G.files.values() if f["module"] == d]
    src = [f for f in files if not f["test"]]
    tst = [f for f in files if f["test"]]
    syms = [s for s in G.syms if s["module"] == d and s["is_type"] and not s["test"]]
    return {"files": len(src), "test_files": len(tst), "loc": sum(f["loc"] for f in src),
            "test_loc": sum(f["loc"] for f in tst), "types": len(syms),
            "layers": dict(Counter(s["layer"] for s in syms).most_common()),
            "packages": sorted({f["pkg"] for f in src if f["pkg"]})[:40]}


def manifest(G: "Graph", A: dict, mods: list, D: dict | None = None) -> dict:
    P, S = G.P, G.syms
    src = [f for f in G.files.values() if not f["test"]]
    tst = [f for f in G.files.values() if f["test"]]
    assets = [r for r in P["files"] if r["data"] is None]
    return {
        "version": VERSION, "parser": PARSER_VERSION, "generated_by": "claude_indexer.py",
        "project": {"name": project_name(P), "root_name": P["root"].name, "build": P["proj"]["build_kind"],
                    "kotlin": P["proj"]["kotlin"], "jvm": P["proj"]["jvm"], "spring_boot": P["proj"]["spring_boot"],
                    "tech": [t for t, _ in G.techs.most_common(20)]},
        "totals": {"modules": len([m for m in mods if m["files"]]), "source_files": len(src), "test_files": len(tst),
                   "other_files": len(assets), "loc": sum(f["loc"] for f in src), "test_loc": sum(f["loc"] for f in tst),
                   "symbols": len(S), "types": sum(1 for s in S if s["is_type"] and not s["test"]),
                   "functions": sum(1 for s in S if s["kind"] == "fun" and not s["test"]),
                   "public_api": sum(1 for s in S if s["vis"] == "public" and not s["test"] and s["kind"] in ("fun", "property") ),
                   "edges": len(G.edges), "entrypoints": len(G.entries),
                   "calls_resolved": G.resolved_calls, "calls_unresolved": G.unresolved_calls,
                   "unresolved_reasons": dict(G.unresolved_reasons),
                   "todos": sum(f["n_todos"] for f in G.files.values()), "parse_errors": sum(1 for f in G.files.values() if f["err"])},
        "health": {"module_cycles": len(A["cycles_modules"]), "package_cycles": len(A["cycles_packages"]),
                   "layer_violations": len(A["violations"]), "god_classes": len(A["god"]),
                   "complex_functions": len(A["complex"]), "dead_candidates": A["dead_total"],
                   "undeclared_deps": len(A["undeclared"]), "unused_deps": len(A["unused"])},
        "discovery": {} if not D else {
            "tables": len(D["res"]["tables"]), "config_keys": len(D["res"]["config"]),
            "profiles": D["res"]["profiles"],
            "topics": len({f["value"] for f in D["facts"] if f["kind"] == "topic"}),
            "external_urls": len({f["value"] for f in D["facts"] if f["kind"] == "url"}),
            "features": len(D["features"]),
            "types_covered_by_tests": len({i for i, t in D["cov"]["cov"].items() if t and G.syms[i]["is_type"]}),
            "conventions": {k: D["conv"][k] for k in ("package_style", "di", "test_libs", "log_libs") if k in D["conv"]},
            "unreachable": len(D.get("reach", {}).get("unreachable", [])),
            "clone_groups": len(D.get("clones", [])),
            "high_risk_files": sum(1 for r in D.get("risk", []) if r["score"] >= 60),
        },
        "files": {k: f"{G.cfg['state_dir']}/{k}.jsonl" for k in
                  ("symbols", "edges", "files", "assets", "modules", "entrypoints",
                   "facts", "features", "tables", "config", "coverage", "risk", "clones", "surface", "reach")},
        "docs": {k: f"{G.cfg['docs_dir']}/{v}" for k, v in
                 (("index", "INDEX.md"), ("tree", "TREE.md"), ("analysis", "ANALYSIS.md"),
                  ("endpoints", "ENDPOINTS.md"), ("flows", "FLOWS.md"), ("api", "api/"), ("graph", "graph/"),
                  ("features", "FEATURES.md"), ("data", "DATA.md"), ("integrations", "INTEGRATIONS.md"),
                  ("config", "CONFIG.md"), ("conventions", "CONVENTIONS.md"), ("tests", "TESTS.md"),
                  ("history", "HISTORY.md"), ("changes", "CHANGES.md"), ("risk", "RISK.md"),
                  ("surface", "SURFACE.md"), ("glossary", "GLOSSARY.md"), ("coupling", "COUPLING.md"))},
        "query": "python claude_indexer.py query <find|show|callers|callees|impl|uses|impact|path|deps|file|members|endpoints|cycles|hotspots|dead|tree|stats>",
    }


def project_name(P: dict) -> str:
    return P["cfg"].get("project_name") or P["proj"].get("name") or P["root"].name


# =========================================================================== #
# Inventario de arquivos nao-fonte
# =========================================================================== #
ASSET_KINDS = [
    ("build", {".gradle", ".kts", ".toml"}, {"pom.xml", "Makefile", "gradlew", "gradlew.bat", "Dockerfile", "docker-compose.yml", "docker-compose.yaml"}),
    ("sql", {".sql"}, set()),
    ("config", {".yml", ".yaml", ".properties", ".conf", ".ini", ".env", ".xml"}, set()),
    ("doc", {".md", ".adoc", ".rst", ".txt"}, set()),
    ("script", {".sh", ".bat", ".ps1", ".py", ".rb"}, set()),
    ("data", {".json", ".csv", ".tsv", ".avsc", ".proto", ".graphql", ".xsd", ".wsdl"}, set()),
    ("web", {".html", ".css", ".js", ".ts", ".tsx", ".vue"}, set()),
    ("ci", set(), {".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"}),
]


def asset_kind(path: str, ext: str) -> str:
    base = path.rsplit("/", 1)[-1]
    if "/.github/workflows/" in "/" + path or base in (".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"):
        return "ci"
    for kind, exts, names in ASSET_KINDS:
        if ext in exts or base in names:
            return kind
    return "other"


_SQL_OBJ = re.compile(r"(?is)\b(create|alter|drop)\s+(?:or\s+replace\s+)?(table|view|index|sequence|procedure|function|trigger|type)\s+(?:if\s+(?:not\s+)?exists\s+)?([\w.\"\[\]`]+)")


def asset_info(root: Path, path: str, ext: str) -> str:
    kind = asset_kind(path, ext)
    try:
        if kind == "sql":
            txt = read_text(root / path, 400_000)
            seen = []
            for op, obj, name in _SQL_OBJ.findall(txt):
                clean = name.strip("\"`[]")
                item = f"{op.upper()} {obj.lower()} {clean}"
                if item not in seen:
                    seen.append(item)
            extra = sorted({t for t in re.findall(r"(?is)\b(?:insert\s+into|update|delete\s+from)\s+([\w.\"]+)", txt)})
            out = seen[:6] + ([f"DML: {', '.join(extra[:5])}"] if extra else [])
            return "; ".join(out)[:200]
        if kind == "config" and ext in (".yml", ".yaml", ".properties", ".conf"):
            txt = read_text(root / path, 200_000)
            if ext in (".yml", ".yaml"):
                keys = list(dict.fromkeys(re.findall(r"^([A-Za-z][\w\-.]*)\s*:", txt, re.M)))
            else:
                keys = list(dict.fromkeys(re.findall(r"^\s*([A-Za-z][\w\-.]*?)(?:\.[\w\-]+)*\s*=", txt, re.M)))
            return "chaves: " + ", ".join(keys[:10]) if keys else ""
        if kind == "doc" and path.rsplit("/", 1)[-1].lower().startswith("readme"):
            for line in read_text(root / path, 100_000).splitlines():
                s = line.strip()
                if s and not s.startswith(("#", "!", "[", "<", "|", "-", "=", "`", ">")):
                    return s[:160]
    except OSError:
        return ""
    return ""


def human_size(n: int) -> str:
    return f"{n} B" if n < 1024 else (f"{n / 1024:.1f} KB" if n < 1024 ** 2 else f"{n / 1024 ** 2:.1f} MB")


# =========================================================================== #
# Escrita de arquivos (idempotente, preserva trechos manuais)
# =========================================================================== #
class Writer:
    def __init__(self, root: Path, dry: bool = False):
        self.root, self.dry = root, dry
        self.root_resolved = root.resolve()
        self.changed: list[str] = []
        self.written: set[str] = set()

    def write(self, rel: str, content: str) -> bool:
        path = self.root / rel
        try:
            if not path.resolve().is_relative_to(self.root_resolved):
                warn(f"escrita fora da raiz do projeto bloqueada: {rel} (confira docs_dir/state_dir no .claude-indexer.json)")
                return False
        except OSError:
            warn(f"nao foi possivel validar o caminho de escrita: {rel}")
            return False
        self.written.add(rel)
        try:
            old = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            old = None
        if old == content:
            return False
        self.changed.append(rel)
        if not self.dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, path)
        return True

    def write_block(self, rel: str, block: str, header: str) -> bool:
        path = self.root / rel
        try:
            old = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            old = None
        wrapped = AUTO_START + "\n" + block.rstrip() + "\n" + AUTO_END
        if old is None:
            new = header.rstrip() + "\n\n" + wrapped + "\n"
        elif AUTO_START in old and AUTO_END in old:
            a = old.index(AUTO_START)
            b = old.index(AUTO_END) + len(AUTO_END)
            new = old[:a] + wrapped + old[b:]
        else:
            new = old.rstrip() + "\n\n" + wrapped + "\n"
        return self.write(rel, new)

    def prune(self, rel_dir: str, suffix: str) -> None:
        """Remove arquivos gerados que nao foram escritos nesta rodada."""
        base = self.root / rel_dir
        if not base.is_dir():
            return
        for p in sorted(base.rglob("*" + suffix)):
            rel = p.relative_to(self.root).as_posix()
            if rel in self.written:
                continue
            try:
                if GEN_MARK not in p.read_text(encoding="utf-8")[:400]:
                    continue
            except (OSError, UnicodeDecodeError):
                continue
            self.changed.append("- " + rel)
            if not self.dry:
                p.unlink(missing_ok=True)


def md_table(head: list[str], rows: list[list], align: str = "") -> list[str]:
    if not rows:
        return []
    sep = ["---"] * len(head)
    for i, a in enumerate(align[:len(head)]):
        sep[i] = {"r": "---:", "c": ":---:"}.get(a, "---")
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(sep) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return out


def loc_(s: dict) -> str:
    return f"`{s['file']}:{s['line']}`"


def code_cell(text: str, n: int = 90) -> str:
    """Celula de tabela markdown com codigo entre crases, truncada de forma segura: corta o
    texto ANTES de fechar as crases, nunca depois — se cortar depois (ex.: f"`{texto}`"[:n]),
    uma assinatura longa (comum com FQN + parametros) perde a crase de fechamento e o bloco de
    codigo continua "aberto" pelo resto do markdown, corrompendo a tabela inteira dali pra
    frente."""
    if len(text) > n:
        text = text[: max(0, n - 1)] + "…"
    return f"`{text}`"


def sig_of(s: dict) -> str:
    s = {"mods": [], "vis": "public", "recv": "", "sig": "", "tparams": [], "vk": "val", **{k: v for k, v in s.items() if v is not None}}
    keep = {"suspend", "override", "open", "abstract", "inline", "operator", "infix", "lateinit", "const", "static", "data", "sealed"}
    kind = s.get("kind", "")
    mods = [m for m in s["mods"] if m in keep and m not in kind]
    vis = "" if s["vis"] == "public" else s["vis"] + " "
    pre = vis + (" ".join(mods) + " " if mods else "")
    if s["kind"] in ("fun", "constructor"):
        recv = (s["recv"] + ".") if s["recv"] else ""
        tp = "<" + ", ".join(s["tparams"]) + "> " if s.get("tparams") and s["kind"] == "fun" else ""
        return f"{pre}fun {tp}{recv}{s['name']}{s['sig']}"
    if s["kind"] == "property":
        recv = (s["recv"] + ".") if s["recv"] else ""
        return f"{pre}{s.get('vk', 'val')} {recv}{s['name']}{s['sig']}"
    if s["kind"] == "typealias":
        return f"{pre}typealias {s['name']} {s['sig']}"
    tp = "<" + ", ".join(s["tparams"]) + ">" if s.get("tparams") else ""
    return f"{pre}{s.get('kind', '')} {s['name']}{tp}{s['sig']}"


def ann_str(s: dict) -> str:
    return " ".join("@" + a for a in s["annots"][:4])


# =========================================================================== #
# Docs: API completa por modulo (publica + privada, parametros)
# =========================================================================== #
def emit_api(G: "Graph", w: "Writer") -> None:
    P, cfg, S = G.P, G.cfg, G.syms
    dd = cfg["docs_dir"]
    by_mod: dict[str, list] = defaultdict(list)
    for s in S:
        if s["is_type"] and s["owner"] < 0:
            by_mod[s["module"]].append(s)
        elif s["kind"] in ("fun", "property", "typealias") and s["owner"] < 0:
            by_mod[s["module"]].append(s)
    children: dict[int, list] = defaultdict(list)
    for s in S:
        if s["owner"] >= 0:
            children[s["owner"]].append(s)

    def render(s: dict, depth: int, out: list) -> None:
        ind = "  " * depth
        head = f"{ind}- **{s['name']}** — `{sig_of(s)}`"
        meta = []
        if s["annots"]:
            meta.append(ann_str(s))
        meta.append(loc_(s))
        if s["kind"] in ("fun", "constructor") and s["cc"] > 1:
            meta.append(f"cc={s['cc']}")
        if s["is_type"]:
            sup = sorted(G.sup.get(s["fqn"], [])) + s.get("ext_supers", [])
            if sup:
                meta.append("herda: " + ", ".join(x.rsplit(".", 1)[-1] for x in sup[:4]))
        out.append(head + "  \n" + ind + "  " + " · ".join(meta))
        if s["doc"]:
            out.append(f"{ind}  > {s['doc']}")
        for c in sorted(children.get(s["id"], []), key=lambda x: (x["kind"] != "constructor", x["line"])):
            if c["kind"] == "enum_entry":
                continue
            render(c, depth + 1, out)
        ents = [c["name"] for c in children.get(s["id"], []) if c["kind"] == "enum_entry"]
        if ents:
            out.append(f"{ind}  - valores: " + ", ".join(ents[:25]))

    for d, m in sorted(P["mods"].items()):
        syms = by_mod.get(d, [])
        if not syms:
            continue
        name = m["id"]
        out = [f"# API do modulo `{name}`", "", GEN_MARK, "",
               f"Caminho `{d}`. Todos os simbolos declarados, incluindo privados, com assinatura, parametros e local.", ""]
        by_file: dict[str, list] = defaultdict(list)
        for s in syms:
            by_file[s["file"]].append(s)
        pubs = sum(1 for s in G.syms if s["module"] == d and s["vis"] == "public" and s["kind"] == "fun")
        privs = sum(1 for s in G.syms if s["module"] == d and s["vis"] == "private" and s["kind"] == "fun")
        out += [f"Funcoes: {pubs} publicas, {privs} privadas.", ""]
        cur_pkg = None
        for path in sorted(by_file):
            fi = G.files[path]
            if fi["pkg"] != cur_pkg:
                cur_pkg = fi["pkg"]
                out += ["", f"## package {cur_pkg or '(raiz)'}", ""]
            tag = " *(teste)*" if fi["test"] else ""
            out.append(f"### `{path}`{tag}")
            if fi["err"]:
                out.append(f"> parse parcial: {fi['err']}")
            out.append("")
            for s in sorted(by_file[path], key=lambda x: x["line"]):
                render(s, 0, out)
            out.append("")
        w.write(f"{dd}/api/{slug(name)}.md", "\n".join(out).rstrip() + "\n")


def slug(gradle_id: str) -> str:
    s = "root" if gradle_id in (":", "") else gradle_id.strip(":").replace(":", "-").replace("/", "-")
    return re.sub(r"[^\w\-.]", "_", s) or "root"


# =========================================================================== #
# Docs: arvore completa
# =========================================================================== #
def emit_tree(G: "Graph", w: "Writer") -> None:
    P, cfg = G.P, G.cfg
    root_name = P["root"].name
    tree: dict = {}
    for r in P["files"]:
        node = tree
        parts = r["path"].split("/")
        for d in parts[:-1]:
            node = node.setdefault(d, {})
        node.setdefault("__files__", []).append(r)
    lines = [f"# Arvore do projeto `{root_name}`", "", GEN_MARK, "",
             "Todos os arquivos versionados (exceto build/ e binarios). `kt`/`java` mostram simbolos e linhas.", "", "```"]
    maxf = cfg["tree_max_files_per_dir"]

    def walk(node: dict, prefix: str) -> None:
        dirs = sorted(k for k in node if k != "__files__")
        files = sorted(node.get("__files__", []), key=lambda r: r["path"])
        items: list = [(d, True) for d in dirs] + [(f, False) for f in files]
        shown = items[:maxf] if len(items) > maxf else items
        for i, (it, isdir) in enumerate(shown):
            last = i == len(shown) - 1 and len(items) == len(shown)
            conn = "`-- " if last else "|-- "
            if isdir:
                lines.append(prefix + conn + it + "/")
                walk(node[it], prefix + ("    " if last else "|   "))
            else:
                base = it["path"].rsplit("/", 1)[-1]
                info = ""
                fi = G.files.get(it["path"])
                if fi:
                    n = sum(1 for i2 in fi["ids"] if G.syms[i2]["is_type"])
                    f2 = sum(1 for i2 in fi["ids"] if G.syms[i2]["kind"] == "fun")
                    info = f"  [{fi['loc']} linhas, {n} tipos, {f2} funcoes]"
                    if fi["test"]:
                        info += " (teste)"
                else:
                    info = f"  [{human_size(it['size'])}]"
                lines.append(prefix + conn + base + info)
        if len(items) > len(shown):
            lines.append(prefix + f"`-- ... +{len(items) - len(shown)} itens")

    walk(tree, "")
    lines += ["```", ""]
    w.write(f"{cfg['docs_dir']}/TREE.md", "\n".join(lines))


# =========================================================================== #
# Docs: INDEX, ANALYSIS, ENDPOINTS, FLOWS, grafos mermaid
# =========================================================================== #
def gradle_cmd(P: dict) -> str:
    if P["proj"]["build_kind"] == "maven":
        return "./mvnw" if (P["root"] / "mvnw").exists() else "mvn"
    return "./gradlew" if (P["root"] / "gradlew").exists() else "gradle"


def test_cmd(P: dict, mid: str) -> str:
    g = gradle_cmd(P)
    if P["proj"]["build_kind"] == "maven":
        return f"{g} -q test" if mid == ":" else f"{g} -q -pl {mid.lstrip(':')} test"
    tgt = "test" if mid == ":" else f"{mid}:test"
    return f"{g} {tgt} --console=plain -q"


def emit_index(G: "Graph", A: dict, man: dict, w: "Writer") -> None:
    P, cfg, S = G.P, G.cfg, G.syms
    dd = cfg["docs_dir"]
    t, h = man["totals"], man["health"]
    L = [f"# Indice do projeto `{project_name(P)}`", "", GEN_MARK, "",
         "Mapa geral gerado pelo indexador. Detalhe por modulo em `" + dd + "/api/`.", "",
         "## Resumo", ""]
    pr = man["project"]
    L += [f"- Build: {pr['build']}" + (f", Kotlin {pr['kotlin']}" if pr["kotlin"] else "") + (f", JVM {pr['jvm']}" if pr["jvm"] else "")
          + (f", Spring Boot {pr['spring_boot']}" if pr["spring_boot"] else ""),
          f"- Tecnologias detectadas: {', '.join(pr['tech'][:12]) or 'n/d'}",
          f"- {t['modules']} modulos, {t['source_files']} arquivos de codigo ({t['loc']} linhas) e {t['test_files']} de teste ({t['test_loc']} linhas)",
          f"- {t['types']} tipos, {t['functions']} funcoes, {t['entrypoints']} entrypoints, {t['edges']} arestas no grafo",
          f"- Chamadas resolvidas: {t['calls_resolved']} (nao resolvidas: {t['calls_unresolved']})",
          f"- Saude: {h['module_cycles']} ciclos de modulo, {h['package_cycles']} de pacote, {h['layer_violations']} violacoes de camada, {h['god_classes']} god classes, {h['dead_candidates']} candidatos a codigo morto",
          ""]
    L += ["## Modulos", ""]
    rows = []
    for d, m in sorted(P["mods"].items()):
        st = module_stats(G, d)
        if not st["files"] and not st["test_files"]:
            continue
        lay = ", ".join(f"{k}:{v}" for k, v in list(st["layers"].items())[:4])
        rows.append([f"`{m['id']}`", f"`{d}`", st["files"], st["loc"], st["types"], lay or "-",
                     ", ".join(f"`{x}`" for x in sorted(m["deps"])[:4]) or "-",
                     f"[api]({dd}/api/{slug(m['id'])}.md)"])
    L += md_table(["Modulo", "Caminho", "Arquivos", "Linhas", "Tipos", "Camadas", "Depende de", "API"], rows, "llrrrlll")
    if A["mcount"]:
        L += ["", "## Dependencias entre modulos (uso real)", ""]
        L += md_table(["De", "Para", "Referencias", "Declarada"],
                      [[f"`{a}`", f"`{b}`", n, "sim" if b in P["mods"][{m['id']: d for d, m in P['mods'].items()}[a]]["deps"] else "**NAO**"]
                       for (a, b), n in A["mcount"].most_common(30)], "llrl")
    if G.entries:
        kinds = Counter(e["kind"] for e in G.entries)
        L += ["", "## Entrypoints", "", ", ".join(f"{k}: {v}" for k, v in kinds.most_common()) + f" — detalhe em `{dd}/ENDPOINTS.md`", ""]
        for e in G.entries[:12]:
            L.append(f"- `{e['label']}` → `{S[e['sym']]['fqn']}` — `{e['file']}:{e['line']}`")
        if len(G.entries) > 12:
            L.append(f"- ... +{len(G.entries) - 12}")
    if A["fan_in"]:
        L += ["", "## Tipos mais referenciados", ""]
        L += md_table(["Tipo", "Usado por", "Camada", "Local"],
                      [[f"`{S[i]['fqn']}`", n, S[i]["layer"], loc_(S[i])] for n, i in A["fan_in"][:10]], "lrll")
    pkgs = Counter(f["pkg"] for f in G.files.values() if f["pkg"] and not f["test"])
    if pkgs:
        L += ["", "## Pacotes principais", ""] + [f"- `{p}` — {n} arquivos" for p, n in pkgs.most_common(15)]
    sc = script_rel(P["root"])
    L += ["", "## Como navegar (para agentes)", "",
          "Consulte o indice antes de abrir arquivos. Reindexar e sempre `python " + sc + "`, sem parametros.", "",
          "| Preciso de | Comando |", "|---|---|",
          f"| Roteiro completo de uma alteracao | `python {sc} query plan <FQN\\|endpoint>` |",
          f"| Localizar simbolo | `python {sc} query find <termo>` |",
          f"| Assinatura, membros, usos | `python {sc} query show <FQN>` |",
          f"| Risco de mudar | `python {sc} query impact <FQN>` |",
          f"| O que mudou na ultima rodada | `python {sc} query changed` |",
          f"| Fatia de uma funcionalidade | `python {sc} query feature <nome>` |",
          f"| Tabelas, topicos, configuracao | `python {sc} query table\\|topic\\|config` |",
          f"| Testes que cobrem | `python {sc} query tests <FQN>` |",
          f"| Codigo analogo e padrao da casa | `python {sc} query similar <FQN>`, `query conventions` |",
          "",
          "Documentos gerados:", "",
          f"- Mapa e estrutura: `{dd}/INDEX.md`, `{dd}/TREE.md`, `{dd}/api/<modulo>.md`, `{dd}/graph/GRAPHS.md`",
          f"- Execucao: `{dd}/ENDPOINTS.md`, `{dd}/FLOWS.md`, `{dd}/FEATURES.md`, `{dd}/RUNTIME.md`",
          f"- Recursos: `{dd}/DATA.md`, `{dd}/INTEGRATIONS.md`, `{dd}/CONFIG.md`",
          f"- Qualidade: `{dd}/ANALYSIS.md`, `{dd}/RISK.md`, `{dd}/TESTS.md`, `{dd}/SURFACE.md`",
          f"- Contexto: `{dd}/CONVENTIONS.md`, `{dd}/GLOSSARY.md`, `{dd}/HISTORY.md`, `{dd}/COUPLING.md`, `{dd}/CHANGES.md`",
          f"- Dados brutos (JSONL, um objeto por linha) em `{cfg['state_dir']}/` para grep e jq.", ""]
    w.write(f"{dd}/INDEX.md", "\n".join(L))


def emit_analysis(G: "Graph", A: dict, w: "Writer") -> None:
    P, cfg, S = G.P, G.cfg, G.syms
    dd = cfg["docs_dir"]
    L = ["# Analise do codigo", "", GEN_MARK, "",
         "Heuristicas do indexador: pontos para revisar, nao vereditos.", ""]
    if A["cycles_modules"]:
        L += ["## Ciclos entre modulos", ""] + [f"- {' -> '.join('`' + x + '`' for x in c)} -> `{c[0]}`" for c in A["cycles_modules"]] + [""]
    if A["undeclared"]:
        L += ["## Dependencias usadas mas nao declaradas", ""]
        L += md_table(["Modulo", "Usa", "Referencias"], [[f"`{a}`", f"`{b}`", n] for a, b, n in sorted(A["undeclared"], key=lambda x: -x[2])[:20]], "llr") + [""]
    if A["unused"]:
        L += ["## Dependencias declaradas e nao usadas", ""] + [f"- `{a}` declara `{b}`" for a, b in A["unused"][:20]] + [""]
    if A["cycles_packages"]:
        L += ["## Ciclos entre pacotes", ""] + [f"- {' -> '.join(c)}" for c in A["cycles_packages"][:10]] + [""]
    if A["cycles_files"]:
        L += ["## Ciclos entre arquivos", ""] + [f"- {' -> '.join('`' + x + '`' for x in c[:6])}" for c in A["cycles_files"][:8]] + [""]
    if A["violations"]:
        L += ["## Violacoes de camada", "",
              "Regras em `.claude-indexer.json` (`forbid`).", ""]
        L += md_table(["Origem", "Alvo", "Regra", "Tipo", "Local"],
                      [[f"`{a}`", f"`{b}`", f"{p[0]} → {p[1]}", ", ".join(k), f"`{f}:{ln}`"] for a, b, p, k, f, ln in A["violations"][:30]]) + [""]
    if A["god"]:
        L += ["## Classes grandes (candidatas a dividir)", ""]
        L += md_table(["Tipo", "Linhas", "Membros", "Camada", "Local"],
                      [[f"`{S[i]['fqn']}`", loc, n, S[i]["layer"], loc_(S[i])] for loc, n, i in A["god"][:15]], "lrrll") + [""]
    if A["complex"]:
        L += ["## Funcoes complexas (complexidade ciclomatica)", ""]
        L += md_table(["Funcao", "CC", "Linhas", "Local"],
                      [[code_cell(S[i]['fqn'] + S[i]['sig']), cc, S[i]["loc"], loc_(S[i])] for cc, i in A["complex"][:20]], "lrrl") + [""]
    if A["long_funs"]:
        L += ["## Funcoes longas", ""] + [f"- `{S[i]['fqn']}` — {n} linhas — {loc_(S[i])}" for n, i in A["long_funs"][:10]] + [""]
    if A["many_params"]:
        L += ["## Funcoes com muitos parametros", ""] + [f"- `{S[i]['fqn']}` — {n} parametros — {loc_(S[i])}" for n, i in A["many_params"][:10]] + [""]
    if A["dead"]:
        L += [f"## Candidatos a codigo morto ({A['dead_total']})", "",
              "Sem referencias no indice. Reflexao, DI e uso externo nao sao detectados: confirme antes de remover.", ""]
        L += md_table(["Simbolo", "Tipo", "Linhas", "Local"],
                      [[f"`{S[i]['fqn']}`", S[i]["kind"], n, loc_(S[i])] for n, i in A["dead"][:40]], "llrl") + [""]
    if A["dupes"]:
        L += ["## Nomes repetidos em pacotes diferentes", ""] + [f"- `{n}`: " + ", ".join(f"`{x}`" for x in v[:6]) for n, v in A["dupes"][:12]] + [""]
    todos = [(f["n_todos"], p, f["todos"]) for p, f in G.files.items() if f["n_todos"]]
    if todos:
        tot = sum(n for n, _, _ in todos)
        L += [f"## TODO / FIXME / HACK ({tot})", ""]
        for n, p, items in sorted(todos, reverse=True)[:15]:
            L.append(f"- `{p}` ({n})" + (f" — {items[0][1]}" if items else ""))
        L.append("")
    errs = [(p, f["err"]) for p, f in G.files.items() if f["err"]]
    if errs:
        L += ["## Arquivos com parse parcial", "", "O indice desses arquivos pode estar incompleto.", ""]
        L += [f"- `{p}` — {e}" for p, e in errs[:20]] + [""]
    w.write(f"{dd}/ANALYSIS.md", "\n".join(L))


def emit_endpoints(G: "Graph", w: "Writer") -> None:
    cfg, S = G.cfg, G.syms
    dd = cfg["docs_dir"]
    L = ["# Entrypoints", "", GEN_MARK, "", "Tudo que inicia execucao: HTTP, listeners, schedulers e mains.", ""]
    by_kind: dict[str, list] = defaultdict(list)
    for e in G.entries:
        by_kind[e["kind"]].append(e)
    titles = {"http": "HTTP", "listener": "Listeners de mensageria/eventos", "schedule": "Agendados",
              "main": "Mains", "app": "Aplicacoes", "custom": "Customizados"}
    for kind in ("http", "listener", "schedule", "app", "main", "custom"):
        items = by_kind.get(kind)
        if not items:
            continue
        L += [f"## {titles[kind]} ({len(items)})", ""]
        rows = []
        if kind == "http":
            for e in items:
                s = S[e["sym"]]
                params = e.get("params") or {}
                params_txt = "; ".join(f"{k}: {', '.join(v)}" for k, v in params.items()) or "-"
                rows.append([f"`{e['label']}`", code_cell(s['fqn'] + (s['sig'] if s['kind'] == 'fun' else ''), 80),
                             code_cell(e["request"], 50) if e.get("request") else "-",
                             code_cell(e["response"], 50) if e.get("response") else "-", params_txt,
                             e.get("status") or "-", code_cell(e["auth"], 40) if e.get("auth") else "-", loc_(s)])
            L += md_table(["Entrada", "Handler", "Request", "Response", "Parametros", "Status", "Auth", "Local"], rows) + [""]
        else:
            for e in items:
                s = S[e["sym"]]
                rows.append([f"`{e['label']}`", code_cell(s['fqn'] + (s['sig'] if s['kind'] == 'fun' else ''), 80),
                             s["module"] if s["module"] != "." else ":", loc_(s)])
            L += md_table(["Entrada", "Handler", "Modulo", "Local"], rows) + [""]
    w.write(f"{dd}/ENDPOINTS.md", "\n".join(L))


def emit_flows(G: "Graph", A: dict, w: "Writer") -> None:
    cfg, S = G.cfg, G.syms
    fl = flows(G, A)
    L = ["# Fluxos de execucao", "", GEN_MARK, "",
         f"Cadeia de chamadas a partir de cada entrypoint (profundidade {cfg['flow_depth']}). "
         "`~>` = implementacao concreta de uma interface; `?` = resolucao incerta; "
         "`⟳` = retorno assincrono/reativo (ver `reactive_wrappers` no .claude-indexer.json).", ""]
    for e, lines in fl:
        s = S[e["sym"]]
        L += [f"## {e['label']}", "", f"`{s['fqn']}` — {loc_(s)}", "", "```"] + lines + ["```", ""]
    if not fl:
        L += ["Nenhum fluxo derivado (sem entrypoints detectados).", ""]
    w.write(f"{cfg['docs_dir']}/FLOWS.md", "\n".join(L))


def mermaid_id(s: str) -> str:
    return re.sub(r"[^\w]", "_", s).strip("_") or "n"


def emit_graphs(G: "Graph", A: dict, w: "Writer") -> None:
    P, cfg, S = G.P, G.cfg, G.syms
    dd = cfg["docs_dir"]
    mods = {m["id"]: d for d, m in P["mods"].items() if module_stats(G, d)["files"]}
    L = ["# Grafos", "", GEN_MARK, "", "## Modulos", "", "```mermaid", "graph LR"]
    for mid in sorted(mods):
        L.append(f"  {mermaid_id(mid)}[\"{mid}\"]")
    declared = {(m["id"], dep) for m in P["mods"].values() for dep in m["deps"]}
    for (a, b), n in sorted(A["mcount"].items()):
        if a in mods and b in mods:
            style = "-->" if (a, b) in declared else "-.->"
            L.append(f"  {mermaid_id(a)} {style}|{n}| {mermaid_id(b)}")
    for a, b in sorted(declared):
        if a in mods and b in mods and (a, b) not in A["mcount"]:
            L.append(f"  {mermaid_id(a)} --> {mermaid_id(b)}")
    L += ["```", "", "Linha tracejada: uso detectado no codigo sem dependencia declarada no build.", ""]
    pk = A["pcount"].most_common(60)
    if pk:
        L += ["## Pacotes (60 arestas mais fortes)", "", "```mermaid", "graph LR"]
        seen = set()
        for (a, b), n in pk:
            for x in (a, b):
                if x not in seen:
                    seen.add(x)
                    short = x.split(".")[-2] + "." + x.split(".")[-1] if x.count(".") >= 1 else x
                    L.append(f"  {mermaid_id(x)}[\"{short}\"]")
            L.append(f"  {mermaid_id(a)} -->|{n}| {mermaid_id(b)}")
        L += ["```", ""]
    types = [i for _, i in A["fan_in"][:14]]
    if types:
        L += ["## Tipos centrais e vizinhos", "", "```mermaid", "graph TD"]
        tset = set(types)
        for i in types:
            L.append(f"  {mermaid_id(S[i]['fqn'])}[\"{S[i]['name']}<br/>{S[i]['layer']}\"]")
        for (a, b, k), _ in sorted(G.edges.items()):
            ta, tb = type_of(G, a), type_of(G, b)
            if ta in tset and tb in tset and ta != tb and k in DEP_KINDS:
                arrow = "==>" if k in ("extends", "implements") else "-->"
                L.append(f"  {mermaid_id(S[ta]['fqn'])} {arrow}|{k}| {mermaid_id(S[tb]['fqn'])}")
        L += ["```", ""]
    out, seen_nodes = [], set()
    for ln in L:
        if re.match(r"^  \w+\[", ln):
            if ln in seen_nodes:
                continue
            seen_nodes.add(ln)
        out.append(ln)
    w.write(f"{dd}/graph/GRAPHS.md", "\n".join(out))


# =========================================================================== #
# CLAUDE.md, AGENTS.md, skill e settings
# =========================================================================== #
def script_rel(root: Path) -> str:
    try:
        return Path(__file__).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return Path(__file__).name


ROOT_HEADER = """# {name}

<!-- Este arquivo e lido por Claude Code e outros agentes. O bloco AUTO e regerado
     pelo indexador; escreva o que for manual FORA dele, que sera preservado. -->

## Objetivo
<!-- 2-3 linhas: o que este projeto faz e para quem. -->

## Regras de negocio e convencoes
<!-- Ex.: mapeamento origem -> destino, regras de reconciliacao, padroes de nome,
     o que nunca pode ser alterado sem aprovacao. -->

## Antes de abrir um PR
- [ ] `{test}`
- [ ] Reindexar: `python {script}`
"""

MODULE_HEADER = """# {mid}

<!-- Bloco AUTO regerado pelo indexador; escreva o que for manual fora dele. -->
"""


def gen_root_block(G: "Graph", A: dict, man: dict, D: dict | None = None) -> str:
    P, cfg, S = G.P, G.cfg, G.syms
    dd, sd = cfg["docs_dir"], cfg["state_dir"]
    t, pr = man["totals"], man["project"]
    sc = script_rel(P["root"])
    L = ["## Visao geral (auto)", ""]
    L.append("- Stack: " + ", ".join(x for x in [f"Kotlin {pr['kotlin']}" if pr["kotlin"] else "Kotlin",
                                                 f"JVM {pr['jvm']}" if pr["jvm"] else "", pr["build"]] if x)
             + (" | " + ", ".join(pr["tech"][:8]) if pr["tech"] else ""))
    L.append(f"- {t['modules']} modulos, {t['source_files']} arquivos ({t['loc']} linhas), {t['types']} tipos, {t['functions']} funcoes")
    L.append(f"- {t['entrypoints']} entrypoints, {t['test_files']} arquivos de teste")
    L += ["", "## Regra de ouro para agentes", "",
          "Nao varra o repositorio com `ls`/`cat`. O indice ja tem assinatura, parametros, local e",
          "relacoes de cada simbolo (publico e privado). Consulte primeiro, leia o arquivo depois:", "",
          "```bash",
          f"python {sc} query find <termo>            # localiza simbolo/arquivo",
          f"python {sc} query show <FQN|Nome>         # assinatura, membros, herdeiros, quem usa",
          f"python {sc} query file <caminho>          # tudo que um arquivo declara",
          f"python {sc} query callers <FQN>           # quem chama",
          f"python {sc} query callees <FQN>           # o que chama",
          f"python {sc} query impact <FQN>            # o que quebra se eu mudar isto (recursivo)",
          f"python {sc} query path <A> <B>            # como A chega em B",
          f"python {sc} query plan <FQN|endpoint>     # roteiro completo da alteracao",
          "```", "",
          "Para comecar uma tarefa, `query plan` entrega de uma vez: fatia afetada, fluxo abaixo,",
          "quem depende, implementacoes a ajustar, tabelas e topicos tocados, testes e comandos.", "",
          "Descoberta ja pronta (nao precisa investigar de novo):", "",
          f"- Tabelas e SQL: `query table [nome]` · `{dd}/DATA.md`",
          f"- Topicos, filas e URLs externas: `query topic [nome]` · `{dd}/INTEGRATIONS.md`",
          f"- Chaves de configuracao e env: `query config [chave]` · `{dd}/CONFIG.md`",
          f"- Fatias por funcionalidade: `query feature [nome]` · `{dd}/FEATURES.md`",
          f"- Testes que cobrem um tipo: `query tests <FQN>` · `{dd}/TESTS.md`",
          f"- Padrao da casa e exemplos canonicos: `query conventions` · `{dd}/CONVENTIONS.md`",
          f"- Codigo analogo para copiar o padrao: `query similar <FQN>`",
          f"- Historico de alteracoes: `query churn` · `{dd}/HISTORY.md`",
          f"- O que mudou na ultima indexacao e o impacto: `query changed` · `{dd}/CHANGES.md`",
          f"- Onde pisar com cuidado: `query risk` · `{dd}/RISK.md`",
          f"- Codigo nao alcancavel e duplicado: `query unreachable`, `query clones`",
          f"- Superficie publica por modulo: `query surface` · `{dd}/SURFACE.md`",
          f"- Arquivos que mudam juntos historicamente: `query coupled <arquivo>` · `{dd}/COUPLING.md`",
          f"- Vocabulario do dominio: `query glossary` · `{dd}/GLOSSARY.md`",
          f"- Quem le e escreve uma propriedade: `query accessors <FQN>`",
          f"- Beans, condicionais, transacoes e cache: `query runtime` · `{dd}/RUNTIME.md`",
          f"- Entidades JPA, colunas e relacoes: `query entity [nome]` · `{dd}/DATA.md`",
          f"- Saude do proprio indice: `query doctor`", "",
          "Depois de alterar codigo, reindexe: `python " + sc + "` (rapido e incremental).", ""]
    L += ["## Mapa de modulos", ""]
    rows = []
    for d, m in sorted(P["mods"].items()):
        st = module_stats(G, d)
        if not st["files"]:
            continue
        rows.append([f"`{m['id']}`", f"`{d}`", st["files"], st["loc"],
                     ", ".join(f"{k}" for k in list(st["layers"])[:3]) or "-",
                     ", ".join(f"`{x}`" for x in sorted(m["deps"])[:3]) or "-"])
    L += md_table(["Modulo", "Caminho", "Arquivos", "Linhas", "Camadas", "Depende de"], rows[:30], "llrrll")
    if len(rows) > 30:
        L.append(f"| ... | +{len(rows) - 30} modulos | | | | |")
    if G.entries:
        L += ["", "## Entrypoints principais", ""]
        for e in G.entries[:10]:
            L.append(f"- `{e['label']}` → `{S[e['sym']]['fqn']}` — `{e['file']}:{e['line']}`")
        if len(G.entries) > 10:
            L.append(f"- ... +{len(G.entries) - 10} em `{dd}/ENDPOINTS.md`")
    L += ["", "## Comandos", "",
          f"- Build: `{gradle_cmd(P)} build`" if P["proj"]["build_kind"] != "maven" else f"- Build: `{gradle_cmd(P)} -q package`",
          f"- Testes de um modulo: `{test_cmd(P, rows[0][0].strip('`') if rows else ':')}`"]
    plugins = {p for m in P["mods"].values() for p in m["plugins"]}
    if any("detekt" in p for p in plugins):
        L.append(f"- Lint: `{gradle_cmd(P)} detekt`")
    if any("ktlint" in p for p in plugins):
        L.append(f"- Formato: `{gradle_cmd(P)} ktlintCheck`")
    h = man["health"]
    alerts = [f"{h['module_cycles']} ciclos entre modulos" if h["module_cycles"] else "",
              f"{h['layer_violations']} violacoes de camada" if h["layer_violations"] else "",
              f"{h['god_classes']} classes grandes" if h["god_classes"] else "",
              f"{h['complex_functions']} funcoes complexas" if h["complex_functions"] else ""]
    alerts = [a for a in alerts if a]
    if alerts:
        L += ["", "## Pontos de atencao", "", "- " + "; ".join(alerts) + f" — ver `{dd}/ANALYSIS.md`"]
    if D:
        disc = man.get("discovery", {})
        L += ["", "## Descoberta automatica", "",
              f"- {disc.get('tables', 0)} tabelas, {disc.get('topics', 0)} topicos, "
              f"{disc.get('external_urls', 0)} URLs externas, {disc.get('config_keys', 0)} chaves de configuracao",
              f"- {disc.get('features', 0)} fatias verticais mapeadas; "
              f"{disc.get('types_covered_by_tests', 0)} tipos alcancados por teste",
              f"- Pacotes {D['conv']['package_style']}; injecao por {D['conv']['di'].split(' (')[0]}; "
              f"testes com {', '.join(D['conv']['test_libs']) or 'n/d'}"]
    L += ["", "## Arquivos gerados (nao editar)", "",
          f"- `{dd}/INDEX.md` mapa geral · `{dd}/TREE.md` arvore · `{dd}/ANALYSIS.md` riscos",
          f"- `{dd}/FEATURES.md` fatias · `{dd}/DATA.md` tabelas · `{dd}/INTEGRATIONS.md` topicos e URLs",
          f"- `{dd}/CONFIG.md` configuracao · `{dd}/CONVENTIONS.md` padrao da casa · `{dd}/TESTS.md` cobertura",
          f"- `{dd}/CHANGES.md` diferencas da ultima rodada · `{dd}/RISK.md` risco · `{dd}/SURFACE.md` API publica",
          f"- `{dd}/RUNTIME.md` beans, condicionais, transacoes e cache",
          f"- `{dd}/GLOSSARY.md` vocabulario · `{dd}/COUPLING.md` acoplamento historico · `{dd}/HISTORY.md` churn",
          f"- `{dd}/ENDPOINTS.md` entradas · `{dd}/FLOWS.md` fluxos · `{dd}/graph/GRAPHS.md` diagramas",
          f"- `{dd}/api/<modulo>.md` API completa (inclui privados e parametros)",
          f"- `{sd}/*.jsonl` dados brutos para grep/jq · `{sd}/manifest.json` resumo",
          "", "## Nao faca", "",
          "- Nao leia `build/`, `.gradle/`, logs, jars ou dumps.",
          "- Nao edite arquivos gerados; edite o codigo ou a secao manual deste arquivo.",
          "- Nao rode a suite inteira quando um modulo ou um teste resolve."]
    return "\n".join(L)


def gen_module_block(G: "Graph", d: str) -> str:
    P, cfg, S = G.P, G.cfg, G.syms
    m = P["mods"][d]
    st = module_stats(G, d)
    L = [f"## Modulo `{m['id']}` (auto)", "",
         f"- {st['files']} arquivos ({st['loc']} linhas), {st['types']} tipos, {st['test_files']} de teste",
         f"- Camadas: " + (", ".join(f"{k} ({v})" for k, v in st["layers"].items()) or "n/d")]
    if m["deps"]:
        L.append("- Depende de: " + ", ".join(f"`{x}`" for x in sorted(m["deps"])))
    if st["packages"]:
        L.append("- Pacotes: " + ", ".join(f"`{p}`" for p in st["packages"][:6]))
    libs = sorted(m["ext"])[:8]
    if libs:
        L.append("- Bibliotecas: " + ", ".join(libs))
    key = [s for s in S if s["module"] == d and s["is_type"] and not s["test"] and s["owner"] < 0
           and s["layer"] not in ("other", "dto", "util", "exception")]
    key.sort(key=lambda s: (-len(G.tfin_get(s["id"])), s["fqn"]))
    if key:
        L += ["", "Tipos principais:", ""]
        for s in key[:12]:
            doc = f" — {s['doc']}" if s["doc"] else ""
            L.append(f"- `{s['name']}` ({s['layer']}) — {loc_(s)}{doc}")
    ents = [e for e in G.entries if S[e["sym"]]["module"] == d]
    if ents:
        L += ["", "Entrypoints: " + ", ".join(f"`{e['label']}`" for e in ents[:8]) + (f" (+{len(ents) - 8})" if len(ents) > 8 else "")]
    L += ["", f"- API completa: `{cfg['docs_dir']}/api/{slug(m['id'])}.md`",
          f"- Testes: `{test_cmd(P, m['id'])}`"]
    return "\n".join(L)


AGENTS_HEADER = """# AGENTS.md — {name}

<!-- Contrato de trabalho para agentes (Devin, Claude Code, Codex e afins).
     O bloco AUTO e regerado pelo indexador; escreva o manual fora dele. -->

## Contexto do produto
<!-- O que o sistema faz, quem usa, o que nao pode quebrar. -->

## Politicas do time
<!-- Ex.: exige teste em toda mudanca; nao alterar contratos publicos sem ADR. -->
"""


def gen_agents_block(G: "Graph", man: dict, D: dict | None = None) -> str:
    P, cfg = G.P, G.cfg
    sc, dd, sd = script_rel(P["root"]), cfg["docs_dir"], cfg["state_dir"]
    t = man["totals"]
    pr = man["project"]
    L = ["## Como este repositorio esta indexado (auto)", "",
         f"Projeto {pr['build']} com {t['modules']} modulos, {t['source_files']} arquivos e {t['loc']} linhas de codigo.",
         f"Stack: {', '.join(x for x in [('Kotlin ' + pr['kotlin']) if pr['kotlin'] else 'Kotlin', ('JVM ' + pr['jvm']) if pr['jvm'] else ''] if x)}"
         + (f". Tecnologias: {', '.join(pr['tech'][:10])}." if pr["tech"] else "."), "",
         "Um indice completo do codigo ja existe neste repositorio. Use-o antes de ler arquivos:", "",
         "| Preciso de | Use |", "|---|---|",
         f"| Achar um simbolo | `python {sc} query find <termo>` |",
         f"| Assinatura, membros e usos de um tipo | `python {sc} query show <FQN>` |",
         f"| O que um arquivo declara | `python {sc} query file <caminho>` |",
         f"| Quem chama / o que chama | `python {sc} query callers\\|callees <FQN>` |",
         f"| Risco de uma alteracao | `python {sc} query impact <FQN>` |",
         f"| Caminho entre dois simbolos | `python {sc} query path <A> <B>` |",
         f"| Implementacoes de uma interface | `python {sc} query impl <FQN>` |",
         f"| Roteiro completo de uma alteracao | `python {sc} query plan <FQN\\|endpoint>` |",
         f"| Tabelas, colunas e quem acessa | `python {sc} query table [nome]` |",
         f"| Topicos, filas e URLs externas | `python {sc} query topic [nome]` |",
         f"| Chaves de configuracao e env | `python {sc} query config [chave]` |",
         f"| Fatia vertical de uma funcionalidade | `python {sc} query feature [nome]` |",
         f"| Testes que cobrem um tipo | `python {sc} query tests <FQN>` |",
         f"| Padrao da casa / exemplo a copiar | `python {sc} query conventions` e `query similar <FQN>` |",
         f"| Por que um simbolo existe | `python {sc} query why <FQN>` |",
         f"| Arquivos mais alterados | `python {sc} query churn` |",
         f"| O que mudou desde a ultima rodada | `python {sc} query changed` |",
         f"| Onde a mudanca e mais arriscada | `python {sc} query risk` |",
         f"| Codigo orfao ou duplicado | `python {sc} query unreachable` e `query clones` |",
         f"| O que o modulo expoe e quem consome | `python {sc} query surface` |",
         f"| Arquivos que mudam juntos | `python {sc} query coupled <arquivo>` |",
         f"| Vocabulario do dominio | `python {sc} query glossary` |",
         f"| Quem le/escreve uma propriedade | `python {sc} query accessors <FQN>` |",
         f"| Quem implementa um tipo em runtime (@Bean) | `python {sc} query runtime` |",
         f"| Entidade JPA, colunas e relacoes | `python {sc} query entity [nome]` |",
         f"| O indice esta completo? | `python {sc} query doctor` |",
         f"| Entradas do sistema | `python {sc} query endpoints` ou `{dd}/ENDPOINTS.md` |",
         f"| Dados brutos para filtrar | `{sd}/symbols.jsonl`, `edges.jsonl`, `files.jsonl` (um JSON por linha) |",
         "", "Todo comando aceita `--json` para saida estruturada.", "",
         "## Fluxo esperado de uma tarefa", "",
         f"1. `python {sc}` para garantir indice atualizado (incremental, segundos).",
         f"2. `python {sc} query plan <alvo>` — sai com fatia, fluxo, dependentes, tabelas, topicos, testes e comandos.",
         f"3. `query similar <FQN>` e `query conventions` para escrever no padrao ja existente.",
         "4. Desenhar a mudanca e implementar. O indice ja fez o levantamento: gaste o esforco no desenho.",
         f"5. Rodar os testes indicados e reindexar com `python {sc}` — sem parametros, ele refaz tudo.",
         f"6. Conferir `{dd}/CHANGES.md` (o que voce mudou e quem depende) e `{dd}/ANALYSIS.md`.",
         "", "## Limites do indice", "",
         "- Resolucao de chamadas e estatica e heuristica: injecao por reflexao, DI dinamica e",
         "  lambdas passadas adiante podem nao aparecer. `?` indica baixa confianca.",
         f"- Chamadas resolvidas: {t['calls_resolved']}; nao resolvidas: {t['calls_unresolved']}.",
         "- 'Codigo morto' e candidato, nunca certeza: confirme antes de remover.",
         "- Tabelas, topicos e chaves vem de literais e anotacoes: nomes montados em tempo de execucao escapam.",
         "- Cobertura de teste aqui e estrutural (existe caminho de chamada), nao cobertura de linha.", ""]
    return "\n".join(L)


SKILL_MD = """---
name: code-index
description: >-
  Consulta o indice de codigo deste repositorio Kotlin/Java (simbolos, assinaturas,
  parametros, chamadas, impacto, endpoints). Use SEMPRE antes de abrir arquivos para
  entender o projeto, localizar uma classe ou funcao, descobrir quem chama o que ou
  avaliar o risco de uma alteracao.
---

# Indice de codigo

{gen}

O indice fica em `{sd}/` (JSONL) e as docs em `{dd}/`. Consulte com:

```bash
python {sc} query find <termo>          # busca por nome, FQN, arquivo ou anotacao
python {sc} query show <FQN|Nome>       # assinatura, membros, herdeiros, usos
python {sc} query members <FQN>         # so os membros, com parametros e visibilidade
python {sc} query file <caminho>        # simbolos e imports de um arquivo
python {sc} query callers <FQN>         # quem chama (use --depth N para recursivo)
python {sc} query callees <FQN>         # o que ele chama
python {sc} query impact <FQN>          # fecho transitivo de quem depende: risco da mudanca
python {sc} query path <A> <B>          # menor caminho de chamadas entre dois simbolos
python {sc} query impl <FQN>            # implementacoes/subclasses
python {sc} query uses <FQN>            # todas as referencias (tipo, injecao, heranca)
python {sc} query deps [<modulo>]       # dependencias entre modulos (real x declarada)
python {sc} query endpoints [<filtro>]  # HTTP, listeners, schedulers, mains
python {sc} query hotspots              # complexidade, tamanho, acoplamento
python {sc} query dead                  # candidatos a codigo morto
python {sc} query cycles                # ciclos de modulo, pacote e arquivo
python {sc} query tree [<prefixo>]      # arvore de diretorios com contagens
python {sc} query stats                 # numeros gerais do projeto

# descoberta ja feita pelo indexador — use em vez de investigar o repositorio
python {sc} query plan <FQN|endpoint>   # ROTEIRO da alteracao: fatia, fluxo, dependentes, testes
python {sc} query feature [<nome>]      # fatia vertical: entrada -> servico -> repo -> tabela -> teste
python {sc} query table [<nome>]        # tabelas, colunas, DDL e quem faz SELECT/INSERT/UPDATE
python {sc} query topic [<nome>]        # topicos, filas, clientes Feign e URLs externas
python {sc} query config [<chave>]      # chaves de configuracao, valores, onde sao usadas, env vars
python {sc} query tests <FQN>           # testes que alcancam o simbolo + comando para roda-los
python {sc} query similar <FQN>         # codigo analogo, para seguir o mesmo padrao
python {sc} query conventions           # padrao da casa e exemplos canonicos por camada
python {sc} query why <FQN>             # de quais entrypoints este codigo e alcancado
python {sc} query churn                 # arquivos mais alterados nos ultimos 12 meses
python {sc} query changed               # o que mudou desde a ultima indexacao, com impacto
python {sc} query risk [<filtro>]       # ranking de risco por arquivo
python {sc} query unreachable           # sem caminho a partir de nenhum entrypoint
python {sc} query clones                # funcoes com corpo estruturalmente identico
python {sc} query surface [<modulo>]    # API publica exposta x realmente consumida
python {sc} query coupled <arquivo>     # arquivos que historicamente mudam junto
python {sc} query glossary              # vocabulario do dominio
python {sc} query accessors <FQN>       # quem le e quem escreve a propriedade
python {sc} query runtime [<filtro>]    # @Bean, @ConditionalOnProperty, @Transactional, cache, retry
python {sc} query entity [<nome>]       # entidades JPA: tabela, colunas, relacoes
python {sc} query doctor                # o que pode estar incompleto no indice e por que
```

Todos aceitam `--json` (saida estruturada) e `--limit N`.

## Regras

- Reindexar e sempre `python {sc}`, sem parametros: ele detecta o que mudou e refaz tudo.
- Ao iniciar qualquer tarefa de alteracao, rode `query plan <alvo>` primeiro. Ele ja traz o
  levantamento inteiro; concentre o esforco em desenhar a mudanca, nao em redescobrir o codigo.
- Prefira o indice a `find`, `ls -R` ou leitura exploratoria de arquivos: e mais barato e mais completo.
- Depois de editar codigo, rode `python {sc}` para reindexar antes de novas consultas.
- `query impact` antes de alterar assinatura publica, remover funcao ou renomear classe.
- `query similar` + `query conventions` antes de criar arquivo novo, para nascer no padrao do projeto.
- `query table` e `query config` antes de mexer em persistencia ou parametros.
- `query runtime` antes de assumir qual implementacao roda: o wiring pode ser por @Bean ou condicional.
- Resultados marcados com `?` tem baixa confianca de resolucao; confirme no codigo.
"""


def emit_agent_files(G: "Graph", A: dict, man: dict, w: "Writer", cfg: dict, D: dict) -> None:
    P = G.P
    name = project_name(P)
    sc = script_rel(P["root"])
    first_mod = next((m["id"] for d, m in sorted(P["mods"].items()) if module_stats(G, d)["files"]), ":")
    w.write_block("CLAUDE.md", gen_root_block(G, A, man, D),
                  ROOT_HEADER.format(name=name, test=test_cmd(P, first_mod), script=sc))
    w.write_block("AGENTS.md", gen_agents_block(G, man, D), AGENTS_HEADER.format(name=name))
    if cfg["module_claude_md"]:
        for d, m in sorted(P["mods"].items()):
            if d != "." and module_stats(G, d)["files"]:
                w.write_block(f"{d}/CLAUDE.md", gen_module_block(G, d), MODULE_HEADER.format(mid=m["id"]))
    if cfg["write_skill"]:
        w.write(".claude/skills/code-index/SKILL.md",
                SKILL_MD.format(gen=GEN_MARK, sc=sc, sd=cfg["state_dir"], dd=cfg["docs_dir"]))
    if cfg["write_settings"]:
        sp = P["root"] / ".claude" / "settings.json"
        if not sp.exists():
            settings = {
                "permissions": {"deny": ["Read(./build/**)", "Read(./**/build/**)", "Read(./.gradle/**)",
                                          "Read(./**/*.log)", "Read(./**/*.jar)", "Read(./**/*.class)",
                                          f"Read(./{cfg['state_dir']}/cache.json)"]},
                "hooks": {"PostToolUse": [{"matcher": "Edit|Write|MultiEdit",
                                            "hooks": [{"type": "command",
                                                       "command": f'python3 "$CLAUDE_PROJECT_DIR/{sc}" "$CLAUDE_PROJECT_DIR" --quiet || true'}]}]},
            }
            w.write(".claude/settings.json", json.dumps(settings, indent=2) + "\n")
    gi = P["root"] / ".gitignore"
    if gi.exists() and cfg["state_dir"].startswith(".claude"):
        try:
            txt = gi.read_text(encoding="utf-8")
            if "cache.json" not in txt and ".claude/index" not in txt:
                w.write(".gitignore", txt.rstrip() + f"\n\n# indice de codigo (cache local)\n{cfg['state_dir']}/cache.json\n")
        except OSError:
            pass


# =========================================================================== #
# Consulta do indice (le os JSONL; nao reparseia o projeto)
# =========================================================================== #
class Store:
    def __init__(self, root: Path, cfg: dict):
        self.root, self.cfg = root, cfg
        sd = root / cfg["state_dir"]
        self.dir = sd
        try:
            self.manifest = json.loads((sd / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise SystemExit(f"Indice nao encontrado em {sd}. Rode: python {script_rel(root)}")
        self.syms: dict[int, dict] = {}
        for r in self._lines("symbols.jsonl"):
            r.setdefault("vis", "public")
            r.setdefault("mods", [])
            r.setdefault("annots", [])
            r.setdefault("params", [])
            r.setdefault("sig", "")
            r.setdefault("doc", "")
            r.setdefault("module", ".")
            r.setdefault("layer", "other")
            self.syms[r["id"]] = r
        self.by_fqn: dict[str, list] = defaultdict(list)
        self.by_name: dict[str, list] = defaultdict(list)
        self.children: dict[int, list] = defaultdict(list)
        for s in self.syms.values():
            self.by_fqn[s["fqn"]].append(s["id"])
            self.by_name[s["name"]].append(s["id"])
            if s.get("owner", -1) is not None and s.get("owner", -1) >= 0:
                self.children[s["owner"]].append(s["id"])
        self.out: dict[int, list] = defaultdict(list)
        self.inc: dict[int, list] = defaultdict(list)
        self.edges = []
        for e in self._lines("edges.jsonl"):
            self.edges.append(e)
            self.out[e["s"]].append(e)
            self.inc[e["d"]].append(e)
        self.files = {r["path"]: r for r in self._lines("files.jsonl")}
        self.assets = {r["path"]: r for r in self._lines("assets.jsonl")}
        self.modules = {r["id"]: r for r in self._lines("modules.jsonl")}
        self.entries = list(self._lines("entrypoints.jsonl"))

    def _lines(self, name: str):
        p = self.dir / name
        try:
            with p.open(encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if ln:
                        yield json.loads(ln)
        except OSError:
            return

    # ---- resolucao ----
    def resolve(self, ref: str, kinds=None) -> list[int]:
        if ref.isdigit() and int(ref) in self.syms:
            return [int(ref)]
        hits = list(self.by_fqn.get(ref, []))
        if not hits:
            hits = list(self.by_name.get(ref, []))
        if not hits and "." in ref:
            owner, _, member = ref.rpartition(".")
            for oid in self.by_fqn.get(owner, []) + self.by_name.get(owner, []):
                hits += [c for c in self.children[oid] if self.syms[c]["name"] == member]
        if not hits:
            low = ref.lower()
            hits = [i for i, s in self.syms.items() if s["fqn"].lower().endswith(low)]
        if kinds:
            f = [h for h in hits if self.syms[h]["kind"] in kinds]
            hits = f or hits
        prim = [h for h in hits if not self.syms[h].get("test")]
        hits = prim or hits
        exact = [h for h in hits if self.syms[h]["fqn"] == ref]
        hits = exact or hits
        return sorted(set(hits), key=lambda i: (-len(self.inc.get(i, [])), self.syms[i]["fqn"], i))

    def need(self, ref: str, kinds=None) -> int:
        hits = self.resolve(ref, kinds)
        if not hits:
            raise SystemExit(f"Nao encontrei '{ref}'. Tente: query find {ref}")
        if len(hits) > 1:
            names = "\n".join(f"  - {self.label(i)} ({self.syms[i]['kind']}) {self.at(i)}" for i in hits[:12])
            warn(f"'{ref}' e ambiguo, usando o primeiro:\n{names}")
        return hits[0]

    # ---- formatacao ----
    def label(self, i: int) -> str:
        return self.syms[i]["fqn"]

    def at(self, i: int) -> str:
        s = self.syms[i]
        return f"{s['file']}:{s['line']}"

    def sig(self, i: int) -> str:
        return sig_of(self.syms[i])

    def line(self, i: int, extra: str = "") -> str:
        s = self.syms[i]
        tag = f" [{s['layer']}]" if s["layer"] not in ("other",) else ""
        return f"{self.sig(i)}{tag}{extra}\n    {self.at(i)}" + (f"\n    {s['doc']}" if s["doc"] else "")


def out_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True))


def walk_edges(st: Store, start: int, depth: int, direction: str, kinds) -> list[tuple[int, int, str, float, int, int]]:
    """BFS no grafo. Retorna (id, profundidade, tipo_da_aresta, confianca, id_do_no_anterior,
    linha_da_chamada). A linha e a evidencia: onde no codigo essa aresta foi extraida (sempre
    dentro do corpo de quem chama, nao da declaracao do alvo)."""
    seen = {start}
    res = []
    q = deque([(start, 0)])
    while q:
        cur, d = q.popleft()
        if d >= depth:
            continue
        table = st.out if direction == "out" else st.inc
        for e in sorted(table.get(cur, []), key=lambda e: (e["k"], e["s"], e["d"])):
            if kinds and e["k"] not in kinds:
                continue
            nxt = e["d"] if direction == "out" else e["s"]
            if nxt in seen:
                continue
            seen.add(nxt)
            res.append((nxt, d + 1, e["k"], e.get("c", 1.0), cur, e.get("l", 0)))
            q.append((nxt, d + 1))
    return res


def call_site(st: Store, direction: str, cur: int, nxt: int, ln: int) -> str:
    """Local do texto que originou a aresta: para 'out' e dentro de quem ja foi visitado (cur);
    para 'in', dentro de quem acabou de ser encontrado (nxt), que e quem faz a chamada."""
    owner = cur if direction == "out" else nxt
    return f"{st.syms[owner]['file']}:{ln}" if ln else st.at(owner)


def cmd_find(st: Store, a) -> None:
    term = " ".join(a.terms).lower()
    rx = re.compile(a.terms[0], re.I) if a.regex and a.terms else None
    hits = []
    for i, s in st.syms.items():
        if a.kind and s["kind"] != a.kind:
            continue
        if a.layer and s["layer"] != a.layer:
            continue
        if not a.tests and s.get("test"):
            continue
        hay = " ".join([s["fqn"], s.get("sig", ""), " ".join(s.get("annots", [])), s.get("doc", ""), s["file"]])
        ok = rx.search(hay) if rx else (term in hay.lower())
        if ok:
            score = (0 if s["name"].lower() == term else (1 if s["name"].lower().startswith(term) else 2), not s["is_type"] if "is_type" in s else 1, len(s["fqn"]))
            hits.append((score, i))
    hits.sort()
    if a.json:
        out_json([{**st.syms[i], "at": st.at(i)} for _, i in hits[:a.limit]])
        return
    if not hits:
        fh = [p for p in list(st.files) + list(st.assets) if term in p.lower()]
        if fh:
            print(f"Nenhum simbolo; arquivos com '{term}':")
            for p in fh[:a.limit]:
                print("  " + p)
        else:
            print(f"Nada encontrado para '{term}'.")
        return
    print(f"{len(hits)} resultado(s) para '{term}':\n")
    for _, i in hits[:a.limit]:
        print(st.line(i) + "\n")
    if len(hits) > a.limit:
        print(f"... +{len(hits) - a.limit} (use --limit)")


def describe(st: Store, i: int, a) -> dict:
    s = st.syms[i]
    kids = sorted(st.children.get(i, []), key=lambda c: (st.syms[c]["kind"] != "constructor", st.syms[c]["line"]))
    callers = [e for e in st.inc.get(i, []) if e["k"] in DEP_KINDS]
    for c in kids:
        callers += [e for e in st.inc.get(c, []) if e["k"] in DEP_KINDS and st.syms[e["s"]].get("owner") != i]
    callees = [e for e in st.out.get(i, []) if e["k"] in CALL_KINDS]
    subs = [e["s"] for e in st.inc.get(i, []) if e["k"] in ("extends", "implements")]
    overs = [e["s"] for e in st.inc.get(i, []) if e["k"] == "overrides"]
    return {"sym": s, "children": kids, "callers": callers, "callees": callees, "subs": subs, "overrides": overs}


def cmd_show(st: Store, a) -> None:
    i = st.need(a.terms[0])
    d = describe(st, i, a)
    s = d["sym"]
    if a.json:
        out_json({"symbol": s, "at": st.at(i),
                  "members": [st.syms[c] for c in d["children"]],
                  "supers": s.get("supers_fq", []) + s.get("ext_supers", []),
                  "subtypes": [st.label(x) for x in d["subs"]],
                  "used_by": sorted({st.label(e["s"]) for e in d["callers"]}),
                  "calls": sorted({st.label(e["d"]) for e in d["callees"]})})
        return
    print("=" * 70)
    print(st.sig(i) + ("  ⟳ async/reativo" if s.get("async") else ""))
    print(f"  {st.at(i)}  ·  modulo {st.syms[i]['module']}  ·  camada {s['layer']}" + ("  ·  TESTE" if s.get("test") else ""))
    if s.get("annots"):
        print("  " + " ".join("@" + x for x in s["annots"]))
    if s.get("coroutine_ops"):
        print("  coroutine: " + ", ".join(s["coroutine_ops"]))
    if s.get("pipeline"):
        print("  pipeline: " + " → ".join(s["pipeline"]))
    if s.get("doc"):
        print("  " + s["doc"])
    sup = s.get("supers_fq", []) + s.get("ext_supers", [])
    if sup:
        print("  herda de: " + ", ".join(sup))
    if d["subs"]:
        print(f"  implementado/estendido por ({len(d['subs'])}): " + ", ".join(st.label(x) for x in d["subs"][:8]))
    if s.get("params"):
        print("\n  Parametros:")
        for pn, pt, *rest in s["params"]:
            pa = rest[0] if rest else []
            role_pa = next((x for x in pa if ann_name_lite(x) in PARAM_ROLE_ANN), pa[0] if pa else None)
            tag = f"  @{role_pa}" if role_pa else ""
            print(f"    - {pn}: {pt or '?'}{tag}")
    if d["children"]:
        pub = [c for c in d["children"] if st.syms[c]["vis"] == "public"]
        oth = [c for c in d["children"] if st.syms[c]["vis"] != "public"]
        print(f"\n  Membros ({len(pub)} publicos, {len(oth)} nao publicos):")
        for c in (d["children"] if a.all else pub + oth)[:a.limit]:
            cs = st.syms[c]
            cc = f"  cc={cs['cc']}" if cs.get("cc", 0) > 1 else ""
            print(f"    {sig_of(cs)}{cc}   (L{cs['line']})")
        if len(d["children"]) > a.limit:
            print(f"    ... +{len(d['children']) - a.limit}")
    if d["callers"]:
        agg = Counter(st.label(e["s"]) for e in d["callers"])
        print(f"\n  Usado por ({len(agg)}):")
        for name, n in agg.most_common(a.limit):
            print(f"    - {name}" + (f" ({n}x)" if n > 1 else ""))
    if d["callees"]:
        agg = Counter(st.label(e["d"]) for e in d["callees"])
        print(f"\n  Chama ({len(agg)}):")
        for name, n in agg.most_common(a.limit):
            print(f"    - {name}" + (f" ({n}x)" if n > 1 else ""))
    print("=" * 70)


def cmd_members(st: Store, a) -> None:
    i = st.need(a.terms[0])
    kids = st.children.get(i, [])
    if a.json:
        out_json([{**st.syms[c], "at": st.at(c)} for c in kids])
        return
    print(f"{st.label(i)} — {len(kids)} membros\n")
    ordered = sorted(kids, key=lambda c: (st.syms[c]["vis"] != "public", st.syms[c]["line"]))
    for c in ordered[:a.limit]:
        s = st.syms[c]
        print(f"  {sig_of(s)}")
        print(f"      L{s['line']}-{s.get('end', s['line'])}" + (f"  cc={s['cc']}" if s.get("cc", 0) > 1 else "")
              + (f"  {s['doc']}" if s["doc"] else ""))
    if len(ordered) > a.limit:
        print(f"  ... +{len(ordered) - a.limit} (use --limit)")


def cmd_graph(st: Store, a, direction: str, kinds, title: str) -> None:
    i = st.need(a.terms[0])
    res = walk_edges(st, i, a.depth, direction, kinds)
    if a.json:
        out_json({"root": st.label(i), "items": [
            {"fqn": st.label(x), "depth": d, "kind": k, "conf": c, "at": st.at(x),
             "evidence": call_site(st, direction, cur, x, ln)}
            for x, d, k, c, cur, ln in res[:a.limit]]})
        return
    print(f"{title}: {st.label(i)}  ({st.at(i)})\n")
    if not res:
        print("  (nenhum)")
        return
    by_depth: dict = defaultdict(list)
    for x, d, k, c, cur, ln in res:
        by_depth[d].append((x, k, c, cur, ln))
    shown = 0
    for d in sorted(by_depth):
        print(f"  nivel {d} ({len(by_depth[d])}):")
        for x, k, c, cur, ln in by_depth[d]:
            if shown >= a.limit:
                break
            shown += 1
            print(f"    - [{k}{'?' if c < 0.7 else ''}] {sig_of(st.syms[x])}")
            print(f"          {st.at(x)}  ·  chamada em {call_site(st, direction, cur, x, ln)}")
        if shown >= a.limit:
            break
    if len(res) > shown:
        print(f"  ... +{len(res) - shown} (use --limit)")


def cmd_impact(st: Store, a) -> None:
    i = st.need(a.terms[0])
    res = walk_edges(st, i, a.depth, "in", DEP_KINDS)
    types, files, mods, tests = set(), set(), set(), set()
    for x, d, k, c, cur, ln in res:
        s = st.syms[x]
        (tests if s.get("test") else files).add(s["file"])
        mods.add(s["module"])
        types.add(x)
    if a.json:
        out_json({"root": st.label(i), "symbols": len(types), "files": sorted(files), "test_files": sorted(tests),
                  "modules": sorted(mods),
                  "items": [{"fqn": st.label(x), "depth": d, "kind": k, "at": st.at(x),
                             "evidence": call_site(st, "in", cur, x, ln)}
                            for x, d, k, _, cur, ln in res[:a.limit]]})
        return
    print(f"Impacto de alterar {st.label(i)} ({st.at(i)})")
    print(f"  profundidade {a.depth}: {len(types)} simbolos, {len(files)} arquivos de codigo, {len(tests)} de teste, {len(mods)} modulos\n")
    by_depth: dict[int, list] = defaultdict(list)
    for x, d, k, c, cur, ln in res:
        by_depth[d].append((x, k, c, cur, ln))
    for d in sorted(by_depth):
        print(f"  nivel {d} ({len(by_depth[d])}):")
        for x, k, c, cur, ln in by_depth[d][:a.limit]:
            print(f"    - [{k}{'?' if c < 0.7 else ''}] {st.label(x)}  {call_site(st, 'in', cur, x, ln)}")
        if len(by_depth[d]) > a.limit:
            print(f"    ... +{len(by_depth[d]) - a.limit}")
    if files:
        print("\n  Arquivos a revisar:")
        for f in sorted(files)[:a.limit]:
            print("    " + f)
    if tests:
        print("\n  Testes que cobrem esse caminho:")
        for f in sorted(tests)[:20]:
            print("    " + f)


def cmd_path(st: Store, a) -> None:
    src, dst = st.need(a.terms[0]), st.need(a.terms[1])
    prev: dict[int, tuple] = {src: None}
    q = deque([src])
    found = False
    while q:
        cur = q.popleft()
        if cur == dst:
            found = True
            break
        for e in st.out.get(cur, []):
            if e["k"] not in DEP_KINDS and e["k"] != "implemented_by":
                continue
            if e["d"] not in prev:
                prev[e["d"]] = (cur, e["k"], e.get("c", 1.0), e.get("l", 0))
                q.append(e["d"])
    if not found:
        msg = f"Sem caminho de chamadas de {st.label(src)} ate {st.label(dst)}."
        out_json({"path": []}) if a.json else print(msg)
        return
    chain = []
    cur = dst
    while cur is not None:
        p = prev[cur]
        chain.append((cur, p[1] if p else "", p[2] if p else 1.0, p[0] if p else None, p[3] if p else 0))
        cur = p[0] if p else None
    chain.reverse()
    if a.json:
        out_json({"path": [{"fqn": st.label(x), "via": k, "conf": c, "at": st.at(x),
                             "evidence": f"{st.syms[prv]['file']}:{ln}" if prv is not None else ""}
                            for x, k, c, prv, ln in chain]})
        return
    print(f"Caminho ({len(chain) - 1} passos):\n")
    for n, (x, k, c, prv, ln) in enumerate(chain):
        arrow = "" if n == 0 else f"  -[{k}{'?' if c < 0.7 else ''}]-> "
        print(f"{'  ' * n}{arrow}{sig_of(st.syms[x])}")
        evidence = f"  ·  chamada em {st.syms[prv]['file']}:{ln}" if prv is not None else ""
        print(f"{'  ' * n}      {st.at(x)}{evidence}")


def cmd_file(st: Store, a) -> None:
    ref = a.terms[0]
    cands = [p for p in st.files if p == ref or p.endswith("/" + ref) or ref in p]
    if not cands:
        cands = [p for p in st.assets if ref in p]
        if cands:
            for p in cands[:a.limit]:
                r = st.assets[p]
                print(f"{p}  [{r['kind']}, {human_size(r['size'])}]" + (f"  {r['info']}" if r.get("info") else ""))
            return
        raise SystemExit(f"Arquivo nao indexado: {ref}")
    path = min(cands, key=len)
    f = st.files[path]
    ids = sorted([i for i, s in st.syms.items() if s["file"] == path], key=lambda i: st.syms[i]["line"])
    if a.json:
        out_json({"file": f, "symbols": [st.syms[i] for i in ids]})
        return
    print(f"{path}")
    print(f"  modulo {f['module']} · package {f['pkg'] or '(raiz)'} · {f['loc']} linhas · {len(ids)} simbolos"
          + (" · TESTE" if f["test"] else ""))
    if f.get("err"):
        print(f"  [parse parcial: {f['err']}]")
    if f.get("imports"):
        print(f"\n  Imports ({len(f['imports'])}): " + ", ".join(f["imports"][:15]) + (" ..." if len(f["imports"]) > 15 else ""))
    print("\n  Declara:")
    for i in ids:
        s = st.syms[i]
        ind = "    " if s.get("owner", -1) >= 0 else "  "
        print(f"{ind}L{s['line']:>5}  {sig_of(s)}")
    if f.get("todos"):
        print("\n  TODOs:")
        for ln, txt in f["todos"][:10]:
            print(f"    L{ln}: {txt}")
    dep_in = sorted({st.syms[e['s']]['file'] for i in ids for e in st.inc.get(i, []) if st.syms[e["s"]]["file"] != path})
    if dep_in:
        print(f"\n  Arquivos que dependem deste ({len(dep_in)}):")
        for p in dep_in[:a.limit]:
            print("    " + p)


def cmd_deps(st: Store, a) -> None:
    if a.json:
        out_json(list(st.modules.values()))
        return
    for mid, m in sorted(st.modules.items()):
        if not m["files"] and not m["test_files"]:
            continue
        if a.terms and a.terms[0] not in mid:
            continue
        print(f"{mid}  ({m['dir']})")
        print(f"  {m['files']} arquivos, {m['loc']} linhas, {m['types']} tipos; camadas: "
              + (", ".join(f"{k}={v}" for k, v in m["layers"].items()) or "-"))
        if m["deps"]:
            print("  depende de: " + ", ".join(m["deps"]))
        if m["deps_test"]:
            print("  em teste: " + ", ".join(m["deps_test"]))
        if m["libs"]:
            print("  libs: " + ", ".join(m["libs"][:12]) + (" ..." if len(m["libs"]) > 12 else ""))
        print()


def cmd_endpoints(st: Store, a) -> None:
    items = st.entries
    if a.terms:
        t = a.terms[0].lower()
        items = [e for e in items if t in e["label"].lower() or t in e["fqn"].lower() or t == e["kind"]]
    if a.json:
        out_json(items)
        return
    cur = None
    for e in items[:a.limit]:
        if e["kind"] != cur:
            cur = e["kind"]
            print(f"\n[{cur}]")
        print(f"  {e['label']}\n      {e['fqn']}  ({e['file']}:{e['line']})")
        if e.get("request"):
            print(f"      request: {e['request']}")
        if e.get("response"):
            print(f"      response: {e['response']}")
        if e.get("params"):
            print("      params: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in e["params"].items()))
        if e.get("status"):
            print(f"      status: {e['status']}")
        if e.get("auth"):
            print(f"      auth: @{e['auth']}")
    print(f"\n{len(items)} entrypoint(s).")


def cmd_impl(st: Store, a) -> None:
    i = st.need(a.terms[0])
    subs = walk_edges(st, i, a.depth, "in", ("extends", "implements"))
    overs = [e["s"] for e in st.inc.get(i, []) if e["k"] == "overrides"]
    for c in st.children.get(i, []):
        overs += [e["s"] for e in st.inc.get(c, []) if e["k"] == "overrides"]
    if a.json:
        out_json({"root": st.label(i), "subtypes": [{"fqn": st.label(x), "depth": d, "at": st.at(x)} for x, d, _, _, _, _ in subs],
                  "overrides": [{"fqn": st.label(x), "at": st.at(x)} for x in sorted(set(overs))]})
        return
    print(f"{st.label(i)}  ({st.at(i)})\n")
    print(f"  Subtipos ({len(subs)}):" if subs else "  Sem subtipos no projeto.")
    for x, d, _, _, _, _ in subs[:a.limit]:
        print(f"{'  ' * d}    - {st.label(x)}  {st.at(x)}")
    if overs:
        print(f"\n  Membros que sobrescrevem ({len(set(overs))}):")
        for x in sorted(set(overs), key=lambda x: st.label(x))[:a.limit]:
            print(f"    - {sig_of(st.syms[x])}  {st.at(x)}")


def cmd_uses(st: Store, a) -> None:
    i = st.need(a.terms[0])
    ids = [i] + st.children.get(i, [])
    rows = []
    for x in ids:
        for e in st.inc.get(x, []):
            rows.append((e["k"], e["s"], x, e.get("c", 1.0), e.get("l", 0)))
    rows.sort(key=lambda r: (r[0], st.label(r[1])))
    if a.json:
        out_json([{"kind": k, "from": st.label(s), "to": st.label(d), "conf": c, "at": f"{st.syms[s]['file']}:{ln}"}
                  for k, s, d, c, ln in rows[:a.limit]])
        return
    print(f"Referencias a {st.label(i)} ({len(rows)}):\n")
    cur = None
    for k, s, d, c, ln in rows[:a.limit]:
        if k != cur:
            cur = k
            print(f"[{k}]")
        print(f"  {st.label(s)} → {st.syms[d]['name']}{'?' if c < 0.7 else ''}")
        print(f"      {st.syms[s]['file']}:{ln}")


def cmd_hotspots(st: Store, a) -> None:
    S = st.syms
    funs = [s for s in S.values() if s["kind"] in ("fun", "constructor") and not s.get("test")]
    types = [s for s in S.values() if s.get("is_type") and not s.get("test")]
    fan = Counter()
    for e in st.edges:
        if e["k"] in DEP_KINDS:
            fan[e["d"]] += 1
    data = {
        "complexidade": [(s["cc"], s["fqn"], st.at(s["id"])) for s in sorted(funs, key=lambda x: -x.get("cc", 0))[:a.limit] if s.get("cc", 0) > 1],
        "tamanho (linhas)": [(s.get("loc", 0), s["fqn"], st.at(s["id"])) for s in sorted(types, key=lambda x: -x.get("loc", 0))[:a.limit]],
        "mais referenciados": [(n, S[i]["fqn"], st.at(i)) for i, n in fan.most_common(a.limit * 3) if S[i].get("is_type")][:a.limit],
    }
    if a.json:
        out_json({k: [{"valor": v, "fqn": f, "at": at} for v, f, at in rows] for k, rows in data.items()})
        return
    for title, rows in data.items():
        print(f"\n## {title}")
        for v, f, at in rows:
            print(f"  {v:>6}  {f}\n          {at}")


def cmd_dead(st: Store, a) -> None:
    path = st.root / st.cfg["docs_dir"] / "ANALYSIS.md"
    inc = Counter()
    for e in st.edges:
        inc[e["d"]] += 1
    entry_ids = {e["sym"] for e in st.entries}
    cands = [s for s in st.syms.values()
             if not s.get("test") and s["vis"] == "public" and inc[s["id"]] == 0
             and s["kind"] in ("class", "interface", "object", "fun", "data class", "abstract class")
             and s["id"] not in entry_ids and not s.get("annots")
             and not any(st.syms[c]["id"] in entry_ids for c in st.children.get(s["id"], []))
             and s["name"] not in EXCL_DEAD_NAMES
             and not ({"operator", "override", "const"} & set(s.get("mods", [])))
             and not (s.get("owner", -1) >= 0 and inc[s["owner"]] > 0)
             and not any(e["k"] in ("extends", "implements") for e in st.out.get(s["id"], []))]
    if a.json:
        out_json([{**s, "at": st.at(s["id"])} for s in cands[:a.limit]])
        return
    print(f"{len(cands)} candidato(s) sem referencia no indice (confirme antes de remover; ver {path}):\n")
    for s in sorted(cands, key=lambda s: -s.get("loc", 0))[:a.limit]:
        print(f"  {s['kind']:12} {s['fqn']}\n      {st.at(s['id'])}")


def cmd_cycles(st: Store, a) -> None:
    decl = {mid: set(m["deps"]) for mid, m in st.modules.items()}
    mod_cycles = sccs(sorted(decl), decl)
    padj = defaultdict(set)
    for e in st.edges:
        if e["k"] not in DEP_KINDS:
            continue
        a_, b_ = st.syms[e["s"]], st.syms[e["d"]]
        if a_.get("test") or b_.get("test"):
            continue
        pa, pb = a_.get("pkg", ""), b_.get("pkg", "")
        if pa and pb and pa != pb:
            padj[pa].add(pb)
    pkg_cycles = sccs(sorted(padj), padj)
    if a.json:
        out_json({"modules": mod_cycles, "packages": pkg_cycles[:20]})
        return
    print(f"Ciclos entre modulos: {len(mod_cycles)}")
    for c in mod_cycles:
        print("  " + " -> ".join(c) + f" -> {c[0]}")
    print(f"\nCiclos entre pacotes: {len(pkg_cycles)}")
    for c in pkg_cycles[:a.limit]:
        print("  " + " -> ".join(c[:8]) + (" ..." if len(c) > 8 else ""))


def cmd_tree(st: Store, a) -> None:
    prefix = a.terms[0].rstrip("/") + "/" if a.terms else ""
    dirs: Counter = Counter()
    locs: Counter = Counter()
    for p, f in st.files.items():
        if not p.startswith(prefix):
            continue
        d = p.rsplit("/", 1)[0] if "/" in p else "."
        dirs[d] += 1
        locs[d] += f["loc"]
    for p in st.assets:
        if p.startswith(prefix):
            dirs[p.rsplit("/", 1)[0] if "/" in p else "."] += 1
    if a.json:
        out_json([{"dir": d, "files": n, "loc": locs[d]} for d, n in sorted(dirs.items())])
        return
    print(f"Arvore completa em {st.cfg['docs_dir']}/TREE.md\n")
    for d, n in sorted(dirs.items())[:a.limit]:
        print(f"  {d + '/':60} {n:>4} arquivos  {locs[d]:>7} linhas")


def cmd_stats(st: Store, a) -> None:
    if a.json:
        out_json(st.manifest)
        return
    m = st.manifest
    print(f"Projeto: {m['project']['name']}  ({m['project']['build']})")
    for k, v in m["project"].items():
        if k not in ("name", "build") and v:
            print(f"  {k}: {v if not isinstance(v, list) else ', '.join(v)}")
    print("\nTotais:")
    for k, v in m["totals"].items():
        print(f"  {k:18} {v}")
    print("\nSaude:")
    for k, v in m["health"].items():
        print(f"  {k:18} {v}")
    print("\nCamadas (tipos):")
    lay = Counter(s["layer"] for s in st.syms.values() if s.get("is_type") and not s.get("test"))
    for k, v in lay.most_common():
        print(f"  {k:18} {v}")




# =========================================================================== #
# Build corporativo: buildSrc, convention plugins, subprojects/allprojects,
# gradle.properties, includeBuild e modulos sem arquivo de build proprio.
# =========================================================================== #
_INCLUDE_VAR = re.compile(r"include\s*\(?\s*([A-Za-z_][\w.]*)\s*\)?")
_SUBPROJ = re.compile(r"\b(subprojects|allprojects)\s*\{")


def block_after(text: str, start: int) -> str:
    """Conteudo de um bloco { } a partir da primeira chave depois de start."""
    i = text.find("{", start)
    if i < 0:
        return ""
    depth = 0
    for j in range(i, min(len(text), i + 200_000)):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j]
    return text[i + 1:]


def scan_shared_build(root: Path, files: set, catalog: dict) -> dict:
    """Dependencias declaradas de forma compartilhada (raiz, buildSrc, convention plugins)."""
    shared = {"all": {"ext": set(), "ext_t": set(), "proj": set(), "proj_t": set(), "typed": set(),
                      "typed_t": set(), "plugins": set()}, "by_plugin": {}}
    for name in ("build.gradle.kts", "build.gradle"):
        if name in files:
            txt = read_text(root / name)
            for m in _SUBPROJ.finditer(txt):
                info = parse_gradle_build(block_after(txt, m.start()), catalog)
                for k in shared["all"]:
                    shared["all"][k] |= info[k]
    for p in sorted(files):
        if not p.startswith(("buildSrc/", "build-logic/", "gradle/plugins/")):
            continue
        if not p.endswith((".gradle.kts", ".kt")):
            continue
        txt = read_text(root / p)
        if not txt:
            continue
        info = parse_gradle_build(txt, catalog)
        if p.endswith(".gradle.kts"):
            pid = p.rsplit("/", 1)[-1][:-len(".gradle.kts")]
            shared["by_plugin"][pid] = info
        else:
            for pid in re.findall(r'id\s*\(\s*"([^"]+)"\s*\)|`([\w.\-]+)`', txt):
                key = pid[0] or pid[1]
                if key:
                    shared["by_plugin"].setdefault(key, info)
    return shared


def gradle_properties(root: Path, files: set) -> dict:
    props: dict[str, str] = {}
    for name in ("gradle.properties", "local.properties"):
        if name in files:
            for line in read_text(root / name).splitlines():
                m = re.match(r"\s*([\w.\-]+)\s*=\s*(.*)", line)
                if m and not line.strip().startswith("#"):
                    props[m.group(1)] = m.group(2).strip()
    return props


def apply_shared(mods: dict, shared: dict) -> None:
    for d, m in mods.items():
        if d == "." and len(mods) > 1:
            continue
        for k, v in shared["all"].items():
            m[k] |= v
        for pid in list(m["plugins"]):
            info = shared["by_plugin"].get(pid)
            if info:
                for k, v in info.items():
                    m[k] |= v


def source_dirs_without_build(root: Path, files: set, mods: dict) -> None:
    """Pastas com src/main mas sem build file: viram modulo mesmo assim."""
    seen = set()
    for p in files:
        m = re.match(r"^((?:[\w.\-]+/)*?[\w.\-]+)/src/(?:main|commonMain|jvmMain|androidMain|test)/", p)
        if not m:
            continue
        d = m.group(1)
        if d in mods or d in seen:
            continue
        seen.add(d)
        parent = d.rsplit("/", 1)[0] if "/" in d else "."
        if parent in mods and parent != ".":
            continue
        mods[d] = {"dir": d, "id": ":" + d.replace("/", ":"), "kind": "dir", "ext": set(), "ext_t": set(),
                   "proj": set(), "proj_t": set(), "typed": set(), "typed_t": set(), "plugins": set(),
                   "build": "", "artifact": "", "deps": set(), "deps_t": set()}


# =========================================================================== #
# Spring e frameworks: wiring por @Bean, condicionais, transacoes, cache
# =========================================================================== #
BEAN_ANN = {"Bean", "Provides", "Singleton", "Factory"}
COND_ANN = {"ConditionalOnProperty", "ConditionalOnMissingBean", "ConditionalOnBean", "ConditionalOnClass",
            "ConditionalOnExpression", "Profile", "Requires"}
RESILIENCE_ANN = {"Retryable", "CircuitBreaker", "RateLimiter", "Bulkhead", "TimeLimiter", "Async", "Recover"}
CACHE_ANN = {"Cacheable", "CacheEvict", "CachePut", "Caching"}
TX_ANN = {"Transactional"}


def spring_wiring(G: "Graph") -> dict:
    """Ligacoes de runtime que o grafo estatico nao ve: @Bean, condicionais, transacoes, cache."""
    S = G.syms
    beans, conds, tx, caches, resil = [], [], [], [], []
    for s in S:
        if s["test"]:
            continue
        annots = {ann_name(a): ann_args(a) for a in s["annots"]}
        owner = S[s["owner"]] if s["owner"] >= 0 else None
        if BEAN_ANN & set(annots) and s["kind"] == "fun":
            ret = first_type_name(s["ret"])
            impls = sorted({c for c, _, _ in s["calls"] if c[:1].isupper()})
            if not ret and impls:
                ret = impls[0]
            beans.append({"fqn": s["fqn"], "at": f"{s['file']}:{s['line']}", "tipo": ret or "?",
                          "implementacao": impls[:3], "modulo": s["module"],
                          "config": owner["fqn"] if owner else "", "sym": s["id"]})
        for an in COND_ANN & set(annots):
            keys = re.findall(r'"([\w.\-]+)"', annots[an])
            conds.append({"fqn": s["fqn"], "at": f"{s['file']}:{s['line']}", "anotacao": an,
                          "valores": keys[:4], "sym": s["id"]})
        if TX_ANN & set(annots):
            tx.append({"fqn": s["fqn"], "at": f"{s['file']}:{s['line']}", "args": annots.get("Transactional", "")[:80],
                       "escopo": "classe" if s["is_type"] else "metodo", "sym": s["id"]})
        for an in CACHE_ANN & set(annots):
            names = re.findall(r'"([^"]+)"', annots[an])
            caches.append({"fqn": s["fqn"], "at": f"{s['file']}:{s['line']}", "anotacao": an, "caches": names[:4]})
        for an in RESILIENCE_ANN & set(annots):
            resil.append({"fqn": s["fqn"], "at": f"{s['file']}:{s['line']}", "anotacao": an,
                          "args": annots[an][:60]})
    return {"beans": beans, "conditions": conds, "transactions": tx, "caches": caches, "resilience": resil}


def bean_edges(G: "Graph", wiring: dict) -> None:
    """Liga interface -> implementacao concreta declarada em @Bean."""
    S = G.syms
    for b in wiring["beans"]:
        s = S[b["sym"]]
        fi = G.files[s["file"]]
        ch = G.chain[s["id"]]
        iface = G.rt(b["tipo"], fi, ch) if b["tipo"] else None
        for impl_name in b["implementacao"]:
            r = G.rt(impl_name, fi, ch)
            if r and r[0] in G.types and iface and iface[0] in G.types and r[0] != iface[0]:
                G.add_edge(G.types[iface[0]]["id"], G.types[r[0]]["id"], "provided_by", s["line"], 0.9)


def topic_edges(G: "Graph", facts: list[dict]) -> None:
    """Liga quem consome um topico/fila a quem publica no MESMO topico como aresta de verdade
    (mesmo padrao de bean_edges/jpa_edges: pos-processamento sobre dado ja extraido, sem
    parsing novo). Direcao proposital "consumidor -> publicador" (nao o contrario): no resto
    do arquivo uma aresta (A, B, k) sempre significa "A depende de B" (e' assim que
    query impact/query path caminham, via DEP_KINDS + walk_edges direcao 'in') — quem consome
    depende de quem publica (se o publicador muda o formato da mensagem, o consumidor quebra),
    entao 'query impact <publicador>' precisa listar o consumidor como impactado.
    Confianca baixa (0.5, mesmo nivel de '_uniq' em G.rt): a correlacao e pelo NOME do topico
    como string — perfis/variaveis de ambiente podem fazer duas strings identicas apontarem
    pra filas diferentes em ambientes diferentes, mesma aproximacao ja aceita no resto do
    arquivo (SEND_CALLS/TOPIC_ANN tambem so correlacionam por string)."""
    by_topic: dict[str, dict[str, set]] = defaultdict(lambda: {"publica": set(), "consome": set()})
    for f in facts:
        if f["kind"] == "topic" and f["role"] in ("publica", "consome"):
            by_topic[f["value"]][f["role"]].add(f["sym"])
    for roles in by_topic.values():
        for c in roles["consome"]:
            for p in roles["publica"]:
                if p != c:
                    G.add_edge(c, p, "consumes_from", G.syms[c]["line"], 0.5)


# =========================================================================== #
# Persistencia: JPA, MyBatis XML, Liquibase XML/YAML
# =========================================================================== #
JPA_REL = {"OneToMany", "ManyToOne", "OneToOne", "ManyToMany", "ElementCollection"}


def jpa_model(G: "Graph", res: dict) -> list[dict]:
    """Entidades JPA: tabela, colunas e relacoes."""
    S = G.syms
    out = []
    for s in S:
        annots = {ann_name(a): ann_args(a) for a in s["annots"]}
        if not (s["is_type"] and ({"Entity", "Table", "Document", "MappedSuperclass"} & set(annots))):
            continue
        tm = re.search(r'(?:name\s*=\s*)?"([^"]+)"', annots.get("Table", "") or annots.get("Document", ""))
        table = clean_ident(tm.group(1)) if tm else s["name"].lower()
        cols, rels = [], []
        for c in S:
            if c["owner"] != s["id"] or c["kind"] != "property":
                continue
            ca = {ann_name(a): ann_args(a) for a in c["annots"]}
            rel = JPA_REL & set(ca)
            cm = re.search(r'name\s*=\s*"([^"]+)"', ca.get("Column", "") or ca.get("JoinColumn", ""))
            if rel:
                target = first_type_name(re.sub(r"^\w+<|>$", "", c["ptype"] or "")) or first_type_name(c["ptype"])
                rels.append({"campo": c["name"], "tipo": sorted(rel)[0], "alvo": target,
                             "coluna": cm.group(1) if cm else ""})
            else:
                cols.append({"campo": c["name"], "coluna": cm.group(1) if cm else c["name"],
                             "id": "Id" in ca, "tipo": c["ptype"]})
        out.append({"tipo": s["fqn"], "tabela": table, "at": f"{s['file']}:{s['line']}",
                    "colunas": cols[:60], "relacoes": rels, "sym": s["id"]})
        e = res["tables"].setdefault(table, {"name": table, "ddl": [], "columns": [], "used_by": [], "ops": set()})
        e["columns"] = list(dict.fromkeys(e["columns"] + [c["coluna"] for c in cols]))[:60]
        e.setdefault("entity", s["fqn"])
    return out


def jpa_edges(G: "Graph", jpa: list[dict]) -> None:
    """Liga entidade -> entidade alvo de cada relacao JPA (@OneToMany/@ManyToOne/@OneToOne/
    @ManyToMany) como aresta de verdade no grafo -- mesmo padrao de bean_edges (resolucao de
    tipo ciente de import via G.rt, mesma aresta por par com confianca por resolucao). Sem
    isso, a relacao so aparecia como texto solto em 'query entity'; com isso, 'query path'/
    'query impact' passam a atravessar entidades relacionadas."""
    S = G.syms
    for e in jpa:
        s = S[e["sym"]]
        fi = G.files.get(s["file"])
        if fi is None:
            continue
        ch = G.chain[s["id"]]
        for rel in e["relacoes"]:
            alvo = rel.get("alvo")
            if not alvo:
                continue
            r = G.rt(alvo, fi, ch)
            if r and r[0] in G.types and r[0] != s["fqn"]:
                G.add_edge(s["id"], G.types[r[0]]["id"], "references", s["line"], r[1])


_XML_TAG = re.compile(r"<(\w+)([^>]*)>", re.S)


def scan_xml_resources(P: dict, res: dict, G: "Graph" = None) -> dict:
    """MyBatis (namespace e SQL) e Liquibase (changelogs XML)."""
    root = P["root"]
    mappers, changes = [], []
    for rec in P["files"]:
        if rec["data"] is not None or rec["ext"] != ".xml":
            continue
        txt = read_text(root / rec["path"], 800_000)
        if not txt:
            continue
        low = txt[:2000].lower()
        if "mybatis" in low or "<mapper" in low:
            ns = re.search(r'<mapper[^>]*namespace\s*=\s*"([^"]+)"', txt)
            stmts = []
            for kind, attrs, body in re.findall(r"<(select|insert|update|delete)([^>]*)>(.*?)</\1>", txt, re.S | re.I):
                sid = re.search(r'id\s*=\s*"([^"]+)"', attrs)
                tables = sorted(_tables_in(re.sub(r"<[^>]+>", " ", body)))
                stmts.append({"tipo": kind.lower(), "id": sid.group(1) if sid else "?", "tabelas": tables})
                ns_fqn = ns.group(1) if ns else ""
                owner = G.types.get(ns_fqn) if (G and ns_fqn) else None
                target = None
                if owner and sid:
                    hits = [h for h in G.members.get(ns_fqn, {}).get(sid.group(1), [])]
                    target = G.syms[hits[0]] if hits else owner
                elif owner:
                    target = owner
                for t in tables:
                    e = res["tables"].setdefault(t, {"name": t, "ddl": [], "columns": [], "used_by": [], "ops": set()})
                    e["ops"].add(kind.upper())
                    e["used_by"].append({"kind": "table", "value": t, "role": kind.lower(),
                                         "fqn": (target["fqn"] if target else (ns_fqn or rec["path"])),
                                         "file": (target["file"] if target else rec["path"]),
                                         "line": (target["line"] if target else 1),
                                         "module": rec["module"], "test": False,
                                         "sym": (target["id"] if target else -1), "via": rec["path"]})
            mappers.append({"arquivo": rec["path"], "namespace": ns.group(1) if ns else "",
                            "statements": stmts[:80]})
        elif "databasechangelog" in low or "liquibase" in low:
            for m in re.finditer(r'<(createTable|dropTable|addColumn|createIndex|renameTable)[^>]*tableName\s*=\s*"([^"]+)"', txt, re.I):
                t = clean_ident(m.group(2))
                e = res["tables"].setdefault(t, {"name": t, "ddl": [], "columns": [], "used_by": [], "ops": set()})
                e["ddl"].append([rec["path"], m.group(1)])
                changes.append({"arquivo": rec["path"], "op": m.group(1), "tabela": t})
            for m in re.finditer(r'<column[^>]*name\s*=\s*"([^"]+)"', txt, re.I):
                pass
    return {"mybatis": mappers, "liquibase": changes}


def scan_android(P: dict, G: "Graph") -> list[dict]:
    """Componentes declarados no AndroidManifest como entrypoints."""
    root = P["root"]
    out = []
    for rec in P["files"]:
        if not rec["path"].endswith("AndroidManifest.xml"):
            continue
        txt = read_text(root / rec["path"], 400_000)
        pkg = re.search(r'package\s*=\s*"([^"]+)"', txt)
        for tag in ("activity", "service", "receiver", "provider"):
            for m in re.finditer(rf'<{tag}[^>]*android:name\s*=\s*"([^"]+)"', txt):
                name = m.group(1)
                fq = (pkg.group(1) + name) if name.startswith(".") and pkg else name
                out.append({"tipo": tag, "classe": fq, "arquivo": rec["path"]})
    return out


# =========================================================================== #
# Discovery avancado: banco, mensageria, integracoes, configuracao, testes,
# convencoes, fatias verticais por funcionalidade e churn do git.
# =========================================================================== #
SQL_VERB = re.compile(r"(?is)\b(select|insert\s+into|update|delete\s+from|merge\s+into|call|exec)\b")
SQL_FROM = re.compile(r"(?is)\b(?:from|join|into|update|table)\s+([a-z_][\w$]*(?:\.[\w$]+)?)")
SQL_DDL = re.compile(r"(?is)\b(create|alter|drop)\s+(?:or\s+replace\s+)?(table|view|index|sequence|materialized\s+view)\s+(?:if\s+(?:not\s+)?exists\s+)?([\w.\"`\[\]]+)")
SQL_DML = re.compile(r"(?is)\b(insert\s+into|update|delete\s+from)\s+([\w.\"`]+)")
SQL_TYPE = r"(?:varchar2?|n?char|number|numeric|decimal|u?int\w*|bigint|smallint|tinyint|serial|bigserial|text|date|datetime|timestamp\w*|boolean|bool|float|double|real|money|blob|clob|bytea|uuid|json\w*|xml|raw|long)"
SQL_COL = re.compile(r"(?i)[\"`\[]?(\w+)[\"`\]]?\s+" + SQL_TYPE + r"\b")
SQL_COL_NOISE = {"constraint", "primary", "foreign", "unique", "check", "key", "index", "table", "create", "add", "column", "not", "null", "default"}
SQL_NOISE = {"select", "where", "set", "values", "dual", "and", "or", "on", "as", "by", "group", "order", "inner",
             "left", "right", "outer", "full", "cross", "using", "when", "then", "case", "null", "not", "exists"}
URL_RE = re.compile(r"""(?i)\b(https?://[^\s"'<>{}|\\^`]+)""")
PATH_RE = re.compile(r"^/[a-zA-Z0-9_{}\-./:]{2,}$")
ENV_CALLS = {"getenv", "getEnv", "env"}
CFG_CALLS = {"getProperty", "getString", "getInt", "getBoolean", "property", "config"}
SPEL = re.compile(r"\$\{([\w.\-]+)(?::[^}]*)?\}")
TOPIC_ANN = {"KafkaListener": "consome", "RabbitListener": "consome", "JmsListener": "consome",
             "SqsListener": "consome", "StreamListener": "consome", "TransactionalEventListener": "consome"}
SEND_CALLS = {"send", "publish", "convertAndSend", "sendDefault", "emit", "produce"}
# Tipos de "infraestrutura" de mensageria (nao sao o payload de negocio) -- pulados na hora de
# achar o parametro que carrega o evento em si (ver _consumer_payload_type).
MSG_INFRA_TYPES = {"Acknowledgment", "ConsumerRecord", "MessageHeaders", "Headers", "Message", "Exchange"}


def _consumer_payload_type(s: dict) -> str:
    """Tipo do payload de um metodo consumidor (@KafkaListener/@SqsListener/...): primeiro
    parametro que nao e anotado @Header nem e um tipo de infraestrutura do framework (
    Acknowledgment, ConsumerRecord cru, etc.) -- mesma pegada lexica/sem resolucao de tipo do
    resto dos "facts" (ver scan_code_facts)."""
    for p in s.get("params", []):
        ptype = p[1] if len(p) > 1 else ""
        pannots = p[2] if len(p) > 2 else []
        if any(ann_name_lite(pa) == "Header" for pa in pannots):
            continue
        if first_type_name(ptype) in MSG_INFRA_TYPES:
            continue
        if ptype:
            return ptype
    return ""
HTTP_CLIENT_CALLS = {"getForObject", "getForEntity", "postForObject", "postForEntity", "exchange", "execute",
                     "retrieve", "newCall", "submit", "request", "call"}
TEST_ANN = {"Test", "ParameterizedTest", "RepeatedTest", "TestFactory", "Property"}
TEST_LIBS = {"org.junit.jupiter": "JUnit 5", "org.junit.Test": "JUnit 4", "io.kotest": "Kotest",
             "io.mockk": "MockK", "org.mockito": "Mockito", "org.assertj": "AssertJ",
             "org.testcontainers": "Testcontainers", "org.springframework.boot.test": "Spring Boot Test",
             "kotlin.test": "kotlin.test"}
LOG_LIBS = {"org.slf4j": "SLF4J", "io.github.oshai": "kotlin-logging", "mu.KotlinLogging": "kotlin-logging",
            "java.util.logging": "java.util.logging", "org.apache.logging.log4j": "Log4j2",
            "ch.qos.logback": "Logback"}
DI_ANN = {"Autowired", "Inject", "Resource", "Value", "Component", "Service", "Repository", "Bean", "Configuration"}


def clean_ident(x: str) -> str:
    return x.strip().strip('"`[]').lower()


def _tables_in(sql: str) -> set:
    out = set()
    for m in SQL_FROM.finditer(sql):
        t = clean_ident(m.group(1))
        if t and t not in SQL_NOISE and not t.isdigit() and len(t) > 1:
            out.add(t)
    return out


def sql_columns(txt: str, m_pos: str) -> list:
    """Colunas da lista entre parenteses de um CREATE TABLE."""
    idx = txt.lower().find(m_pos.lower())
    if idx < 0:
        return []
    start = txt.find("(", idx)
    if start < 0:
        return []
    depth, end = 0, len(txt)
    for j in range(start, min(len(txt), start + 20000)):
        if txt[j] == "(":
            depth += 1
        elif txt[j] == ")":
            depth -= 1
            if depth == 0:
                end = j
                break
    body = txt[start + 1:end]
    cols = []
    for chunk in re.split(r",(?![^()]*\))", body):
        c = chunk.strip()
        m = SQL_COL.match(c)
        if m and m.group(1).lower() not in SQL_COL_NOISE:
            cols.append(m.group(1))
    return cols


def scan_resources(P: dict, G: "Graph") -> dict:
    """Le SQL, YAML e properties das pastas de recursos."""
    root = P["root"]
    tables: dict[str, dict] = {}
    cfg_keys: dict[str, dict] = {}
    profiles: set = set()
    for rec in P["files"]:
        if rec["data"] is not None:
            continue
        path, ext = rec["path"], rec["ext"]
        kind = asset_kind(path, ext)
        if kind == "sql":
            txt = read_text(root / path, 800_000)
            for op, obj, name in SQL_DDL.findall(txt):
                t = clean_ident(name)
                if obj.lower().startswith(("table", "materialized")) or obj.lower() == "view":
                    e = tables.setdefault(t, {"name": t, "ddl": [], "columns": [], "used_by": [], "ops": set()})
                    e["ddl"].append([path, op.upper() + " " + obj.lower()])
                    if op.lower() == "create":
                        cols = sql_columns(txt, m_pos=name)
                        if cols:
                            e["columns"] = list(dict.fromkeys(e["columns"] + cols))[:60]
            for op, name in SQL_DML.findall(txt):
                t = clean_ident(name)
                e = tables.setdefault(t, {"name": t, "ddl": [], "columns": [], "used_by": [], "ops": set()})
                e["ops"].add(op.split()[0].upper())
        elif kind == "config" and ext in (".yml", ".yaml", ".properties", ".conf"):
            txt = read_text(root / path, 400_000)
            base = path.rsplit("/", 1)[-1]
            m = re.match(r"application-([\w\-]+)\.(ya?ml|properties)$", base)
            if m:
                profiles.add(m.group(1))
            keys = flatten_config(txt, ext)
            for k, v in keys.items():
                e = cfg_keys.setdefault(k, {"key": k, "files": [], "values": [], "used_by": []})
                if path not in e["files"]:
                    e["files"].append(path)
                if v and len(e["values"]) < 4 and v not in e["values"]:
                    e["values"].append(v)
    return {"tables": tables, "config": cfg_keys, "profiles": sorted(profiles)}


def flatten_config(txt: str, ext: str) -> dict:
    out: dict[str, str] = {}
    if ext in (".properties", ".conf"):
        for line in txt.splitlines():
            m = re.match(r"\s*([\w.\-\[\]]+)\s*[=:]\s*(.*)", line)
            if m and not line.strip().startswith(("#", "!")):
                out[m.group(1)] = m.group(2).strip()[:60]
        return out
    stack: list[tuple[int, str]] = []
    for raw in txt.splitlines():
        if not raw.strip() or raw.strip().startswith("#") or raw.strip().startswith("---"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        m = re.match(r"\s*([\w.\-]+)\s*:(.*)$", raw)
        if not m:
            continue
        key, rest = m.group(1), m.group(2).strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        full = ".".join([k for _, k in stack] + [key])
        if rest and not rest.startswith("#"):
            out[full] = rest[:60]
        else:
            stack.append((indent, key))
    return out


def scan_code_facts(G: "Graph", res: dict) -> dict:
    """Extrai fatos do codigo: tabelas usadas, topicos, URLs, chaves de config, env."""
    S = G.syms
    facts: list[dict] = []
    tables, cfg = res["tables"], res["config"]

    def fact(kind: str, value: str, sym: dict, role: str = "", line: int = 0, **extra) -> None:
        d = {"kind": kind, "value": value[:160], "role": role, "sym": sym["id"], "fqn": sym["fqn"],
             "file": sym["file"], "line": line or sym["line"], "module": sym["module"], "test": sym["test"]}
        d.update({k: v for k, v in extra.items() if v})
        facts.append(d)

    for s in S:
        annots = {ann_name(a): ann_args(a) for a in s["annots"]}
        # --- persistencia por anotacao ---
        for an in ("Table", "Entity", "Document"):
            if an in annots:
                m = re.search(r'(?:name\s*=\s*)?"([^"]+)"', annots[an])
                if m:
                    fact("table", clean_ident(m.group(1)), s, "entidade")
                elif an in ("Entity", "Document"):
                    fact("table", s["name"].lower(), s, "entidade")
        if "Query" in annots:
            q = annots["Query"]
            for t in _tables_in(q):
                fact("table", t, s, "query")
        # --- strings do corpo ---
        for raw, ln in s["strs"]:
            low = raw.lower()
            if SQL_VERB.search(raw) and (" from " in low or " into " in low or low.startswith("update") or " set " in low):
                for t in _tables_in(raw):
                    op = ("SELECT" if low.lstrip().startswith("select") else
                          "INSERT" if "insert" in low[:20] else
                          "UPDATE" if low.lstrip().startswith("update") else
                          "DELETE" if "delete" in low[:20] else "SQL")
                    fact("table", t, s, op.lower(), ln)
            for u in URL_RE.findall(raw):
                fact("url", u, s, "chamada externa", ln)
            for k in SPEL.findall(raw):
                if k in cfg or "." in k:
                    fact("config", k, s, "uso", ln)
        # --- mensageria ---
        for an, role in TOPIC_ANN.items():
            if an in annots:
                payload = _consumer_payload_type(s) if role == "consome" else ""
                for t in re.findall(r'"([^"]+)"', annots[an]):
                    if not t.startswith("$") or True:
                        fact("topic", SPEL.sub(r"${\1}", t), s, role, payload=payload)
        for name, recv, ln in s["calls"]:
            if name in SEND_CALLS:
                for raw, sl in s["strs"]:
                    if abs(sl - ln) <= 1 and ("." in raw or "-" in raw or "_" in raw) and " " not in raw and len(raw) < 80:
                        fact("topic", raw, s, "publica", ln)
                        break
            elif name in ENV_CALLS and recv in ("System", "Env", "ProcessBuilder"):
                for raw, sl in s["strs"]:
                    if abs(sl - ln) <= 1 and raw.isupper():
                        fact("env", raw, s, "uso", ln)
                        break
            elif name in CFG_CALLS:
                for raw, sl in s["strs"]:
                    if abs(sl - ln) <= 1 and "." in raw and " " not in raw:
                        fact("config", raw, s, "uso", ln)
                        break
            elif name in HTTP_CLIENT_CALLS:
                for raw, sl in s["strs"]:
                    if abs(sl - ln) <= 1 and (raw.startswith("http") or PATH_RE.match(raw)):
                        fact("url", raw, s, "chamada externa", ln)
                        break
        # --- @Value / @ConfigurationProperties ---
        if "Value" in annots:
            for k in SPEL.findall(annots["Value"]):
                fact("config", k, s, "injecao")
        if "ConfigurationProperties" in annots:
            m = re.search(r'"([^"]+)"', annots["ConfigurationProperties"])
            if m:
                fact("config", m.group(1) + ".*", s, "prefixo")
        if "FeignClient" in annots:
            nm = re.search(r'(?:name|value)\s*=\s*"([^"]+)"', annots["FeignClient"]) or re.search(r'"([^"]+)"', annots["FeignClient"])
            url = re.search(r'url\s*=\s*"([^"]+)"', annots["FeignClient"])
            fact("service", (nm.group(1) if nm else s["name"]), s, "feign")
            if url:
                fact("url", url.group(1), s, "feign")
    # liga fatos de volta aos recursos
    for f in facts:
        if f["kind"] == "table":
            e = res["tables"].setdefault(f["value"], {"name": f["value"], "ddl": [], "columns": [], "used_by": [], "ops": set()})
            e["used_by"].append(f)
            if f["role"] not in ("entidade", "query"):
                e["ops"].add(f["role"].upper())
        elif f["kind"] == "config":
            key = f["value"].rstrip(".*")
            e = res["config"].get(key)
            if e is None:
                for k in res["config"]:
                    if k.startswith(key + "."):
                        res["config"][k]["used_by"].append(f)
                e = res["config"].setdefault(key, {"key": key, "files": [], "values": [], "used_by": []})
            e["used_by"].append(f)
    return {"facts": facts}


def build_coverage(G: "Graph") -> dict:
    """Quais testes exercitam cada simbolo (fecho de chamadas a partir de cada teste)."""
    S = G.syms
    adj: dict[int, list] = defaultdict(list)
    impl: dict[int, list] = defaultdict(list)
    for (a, b, k), (ln, c) in G.edges.items():
        if k in ("calls", "instantiates") and c >= 0.5:
            adj[a].append(b)
        elif k == "overrides":
            impl[b].append(a)
    tests = [s for s in S if s["test"] and (s["kind"] == "fun" or s["is_type"])
             and (any(ann_name(x) in TEST_ANN for x in s["annots"]) or s["kind"] == "fun")]
    cov: dict[int, set] = defaultdict(set)
    for t in tests:
        seen = {t["id"]}
        q = deque([(t["id"], 0)])
        while q:
            cur, d = q.popleft()
            if d > 6:
                continue
            for nxt in adj.get(cur, []) + impl.get(cur, []):
                if nxt in seen:
                    continue
                seen.add(nxt)
                if not S[nxt]["test"]:
                    cov[nxt].add(t["id"])
                    ow = S[nxt]["owner"]
                    if ow >= 0:
                        cov[ow].add(t["id"])
                q.append((nxt, d + 1))
    return {"cov": cov, "tests": [t["id"] for t in tests]}


def detect_conventions(G: "Graph", res: dict) -> dict:
    S, P = G.syms, G.P
    imports = Counter()
    for f in G.files.values():
        for fq, _, _ in f["raw_imports"]:
            imports[fq] += 1
    def lib(table):
        hits = Counter()
        for fq, n in imports.items():
            for pref, label in table.items():
                if fq.startswith(pref):
                    hits[label] += n
        return [k for k, _ in hits.most_common(4)]
    types = [s for s in S if s["is_type"] and not s["test"] and s["owner"] < 0]
    ctor_di = sum(1 for s in types if s["inject"])
    field_di = sum(1 for s in S if s["kind"] == "property" and any(ann_name(a) in ("Autowired", "Inject") for a in s["annots"]))
    suffixes = Counter()
    for s in types:
        m = re.search(r"[A-Z][a-z]+$", s["name"])
        if m and len(s["name"]) > len(m.group()):
            suffixes[m.group()] += 1
    pkg_tail = Counter(f["pkg"].split(".")[-1] for f in G.files.values() if f["pkg"] and not f["test"])
    layer_first = sum(pkg_tail[x] for x in ("controller", "service", "repository", "domain", "dto", "model", "config", "mapper"))
    funs = [s for s in S if s["kind"] == "fun" and not s["test"]]
    test_funs = [s for s in S if s["kind"] == "fun" and s["test"]]
    bang = sum(1 for f in G.files.values() if f["lang"] == "kt")
    exc = [s for s in S if s["is_type"] and s["name"].endswith(("Exception", "Error")) and not s["test"]]
    return {
        "test_libs": lib(TEST_LIBS), "log_libs": lib(LOG_LIBS),
        "di": ("construtor" if ctor_di >= field_di else "campo/@Autowired") + f" ({ctor_di} por construtor, {field_di} por campo)",
        "suffixes": suffixes.most_common(10),
        "package_style": "por camada" if layer_first >= len(G.files) * 0.3 else "por funcionalidade/dominio",
        "avg_file_loc": round(sum(f["loc"] for f in G.files.values() if not f["test"]) / max(1, sum(1 for f in G.files.values() if not f["test"]))),
        "avg_fun_loc": round(sum(s["loc"] for s in funs) / max(1, len(funs)), 1),
        "test_ratio": round(len(test_funs) / max(1, len(funs)), 2),
        "exceptions": [s["name"] for s in exc[:8]],
        "profiles": res["profiles"],
        "langs": dict(Counter(f["lang"] for f in G.files.values())),
        "suspend": sum(1 for s in funs if "suspend" in s["mods"]),
        "kt_files": bang,
    }


def git_name_only_prefix(root: Path) -> str:
    """'git log --name-only' sempre devolve caminhos relativos ao topo do repositorio, ao
    contrario de 'ls-files' que respeita -C. Se root for um subdiretorio do repo (ex.: um
    modulo 'app/' dentro de um monorepo), esse e o prefixo a remover para casar com os
    caminhos (relativos a root) usados no resto do indice. Vazio se root ja for o topo."""
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - sem git: nada a ajustar
        return ""
    rel = os.path.relpath(str(root.resolve()), top)
    return "" if rel == "." else rel.replace(os.sep, "/") + "/"


def git_churn(root: Path, months: int = 12, max_commits: int = 4000, quiet: bool = False) -> dict:
    """Arquivos mais alterados e data da ultima alteracao (se houver git)."""
    if not quiet:
        print("  analisando historico do git (churn)...", file=sys.stderr)
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", f"--since={months}.months", "--no-merges", f"-n{max_commits}",
             "--pretty=format:@%H|%at|%an", "--name-only"],
            capture_output=True, text=True, timeout=120, check=True, errors="replace").stdout
    except Exception:  # noqa: BLE001 - sem git ou repositorio vazio
        return {}
    prefix = git_name_only_prefix(root)
    churn: dict[str, dict] = {}
    ts, author = 0, ""
    for line in out.splitlines():
        if line.startswith("@"):
            parts = line[1:].split("|")
            ts = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            author = parts[2] if len(parts) > 2 else ""
        elif line.strip():
            path = line.strip()
            if prefix:
                if not path.startswith(prefix):
                    continue
                path = path[len(prefix):]
            e = churn.setdefault(path, {"commits": 0, "last": 0, "authors": Counter()})
            e["commits"] += 1
            e["last"] = max(e["last"], ts)
            if author:
                e["authors"][author] += 1
    return churn


def build_features(G: "Graph", facts: list, cov: dict) -> list[dict]:
    """Fatia vertical por entrypoint: arquivos, camadas, tabelas, topicos, config e testes."""
    S = G.syms
    adj: dict[int, list] = defaultdict(list)
    for (a, b, k), (ln, c) in G.edges.items():
        if k in ("calls", "instantiates") and c >= 0.5:
            adj[a].append(b)
        elif k == "overrides":
            adj[b].append(a)
    by_sym: dict[int, list] = defaultdict(list)
    for f in facts:
        by_sym[f["sym"]].append(f)
    groups: dict[int, list] = defaultdict(list)
    for e in G.entries:
        if e["kind"] in ("http", "listener", "schedule", "main", "custom"):
            s = S[e["sym"]]
            groups[s["owner"] if s["owner"] >= 0 else s["id"]].append(e)
    out = []
    for owner, ents in sorted(groups.items(), key=lambda kv: S[kv[0]]["fqn"]):
        seen = set()
        q = deque((e["sym"], 0) for e in ents)
        seen.update(x for x, _ in q)
        reach: list[int] = []
        while q:
            cur, d = q.popleft()
            reach.append(cur)
            if d >= 8:
                continue
            for nxt in adj.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append((nxt, d + 1))
        files = sorted({S[i]["file"] for i in reach if not S[i]["test"]})
        tables = sorted({f["value"] for i in reach for f in by_sym.get(i, []) if f["kind"] == "table"})
        topics = sorted({f["value"] for i in reach for f in by_sym.get(i, []) if f["kind"] == "topic"})
        urls = sorted({f["value"] for i in reach for f in by_sym.get(i, []) if f["kind"] == "url"})
        cfgs = sorted({f["value"] for i in reach for f in by_sym.get(i, []) if f["kind"] in ("config", "env")})
        tests = sorted({S[t]["file"] for i in reach for t in cov.get(i, ())})
        layers = sorted({S[i]["layer"] for i in reach if S[i]["layer"] not in ("other", "test")})
        out.append({
            "name": S[owner]["name"], "fqn": S[owner]["fqn"], "module": S[owner]["module"],
            "entries": [e["label"] for e in ents], "entry_syms": [e["sym"] for e in ents],
            "symbols": len(reach), "files": files, "layers": layers, "tables": tables, "topics": topics,
            "urls": urls[:10], "config": cfgs[:20], "tests": tests,
            "modules": sorted({S[i]["module"] for i in reach}),
            "at": f"{S[owner]['file']}:{S[owner]['line']}",
        })
    return out


# =========================================================================== #
# Docs do discovery avancado
# =========================================================================== #
def emit_data(G: "Graph", D: dict, w: "Writer") -> None:  # noqa: D401
    cfg, S = G.cfg, G.syms
    tables = D["res"]["tables"]
    L = ["# Mapa de dados", "", GEN_MARK, "",
         "Tabelas encontradas em DDL, anotacoes e SQL embutido no codigo, com quem as acessa.", ""]
    if not tables:
        L.append("Nenhuma tabela detectada.")
    rows = []
    for name, t in sorted(tables.items()):
        ops = sorted(t["ops"] | {f["role"].upper() for f in t["used_by"] if f["role"] not in ("entidade", "query")})
        rows.append([f"`{name}`", ", ".join(ops) or "-", len({f['fqn'] for f in t['used_by']}),
                     len(t["columns"]), ", ".join(f"`{p}`" for p, _ in t["ddl"][:2]) or "-"])
    L += md_table(["Tabela", "Operacoes", "Simbolos", "Colunas", "DDL"], rows, "llrrl") + [""]
    for name, t in sorted(tables.items()):
        if not t["used_by"] and not t["columns"]:
            continue
        L += [f"## `{name}`", ""]
        if t["columns"]:
            L.append("Colunas: " + ", ".join(t["columns"]) + "")
        if t["ddl"]:
            L.append("DDL: " + ", ".join(f"`{p}` ({op})" for p, op in t["ddl"][:6]))
        if t["used_by"]:
            L += ["", "Acessos:", ""]
            for f in sorted(t["used_by"], key=lambda f: (f["fqn"], f["line"]))[:20]:
                L.append(f"- [{f['role']}] `{f['fqn']}` — `{f['file']}:{f['line']}`")
        L.append("")
    L += persistence_sections(D)
    w.write(f"{cfg['docs_dir']}/DATA.md", "\n".join(L))


def emit_integrations(G: "Graph", D: dict, w: "Writer") -> None:
    cfg = G.cfg
    facts = D["facts"]
    topics: dict[str, list] = defaultdict(list)
    urls: dict[str, list] = defaultdict(list)
    svcs: dict[str, list] = defaultdict(list)
    for f in facts:
        if f["kind"] == "topic":
            topics[f["value"]].append(f)
        elif f["kind"] == "url":
            urls[f["value"]].append(f)
        elif f["kind"] == "service":
            svcs[f["value"]].append(f)
    L = ["# Integracoes", "", GEN_MARK, "",
         "Mensageria, servicos externos e URLs encontradas no codigo.", ""]
    if topics:
        L += ["## Topicos e filas", ""]
        rows = []
        for t, fs in sorted(topics.items()):
            cons = [f for f in fs if f["role"] == "consome"]
            prod = [f for f in fs if f["role"] == "publica"]
            payloads = dict.fromkeys(f["payload"] for f in cons if f.get("payload"))
            rows.append([f"`{t}`", ", ".join(f"`{x['fqn']}`" for x in cons[:3]) or "-",
                         ", ".join(f"`{x['fqn']}`" for x in prod[:3]) or "-",
                         ", ".join(f"`{p}`" for p in list(payloads)[:3]) or "-"])
        L += md_table(["Topico", "Consumido por", "Publicado por", "Payload"], rows) + [""]
    if svcs:
        L += ["## Clientes de servicos (Feign e afins)", ""]
        L += [f"- `{k}` — " + ", ".join(f"`{f['fqn']}` (`{f['file']}:{f['line']}`)" for f in v[:3]) for k, v in sorted(svcs.items())] + [""]
    if urls:
        L += ["## URLs e endpoints externos", ""]
        rows = [[f"`{u}`", ", ".join(f"`{f['fqn']}`" for f in v[:2]), f"`{v[0]['file']}:{v[0]['line']}`"]
                for u, v in sorted(urls.items())[:60]]
        L += md_table(["URL", "Usado em", "Local"], rows) + [""]
    if not (topics or urls or svcs):
        L.append("Nenhuma integracao externa detectada.")
    w.write(f"{cfg['docs_dir']}/INTEGRATIONS.md", "\n".join(L))


def emit_config(G: "Graph", D: dict, w: "Writer") -> None:
    cfg = G.cfg
    keys = D["res"]["config"]
    envs: dict[str, list] = defaultdict(list)
    for f in D["facts"]:
        if f["kind"] == "env":
            envs[f["value"]].append(f)
    L = ["# Configuracao", "", GEN_MARK, "",
         "Chaves declaradas nos arquivos de configuracao e onde o codigo as usa. "
         "Chave usada no codigo e ausente dos arquivos costuma vir do ambiente ou do deploy.", ""]
    if D["res"]["profiles"]:
        L += ["Perfis encontrados: " + ", ".join(f"`{p}`" for p in D["res"]["profiles"]), ""]
    used = [(k, v) for k, v in sorted(keys.items()) if v["used_by"]]
    unused = [k for k, v in sorted(keys.items()) if not v["used_by"] and v["files"]]
    undeclared = sorted({f["value"] for f in D["facts"] if f["kind"] == "config" and not keys.get(f["value"].rstrip(".*"), {}).get("files")})
    if used:
        L += ["## Chaves usadas pelo codigo", ""]
        rows = [[f"`{k}`", ", ".join(v["values"][:2]) or "-", ", ".join(f"`{x}`" for x in v["files"][:2]),
                 ", ".join(f"`{f['fqn']}`" for f in v["used_by"][:2])] for k, v in used[:80]]
        L += md_table(["Chave", "Valor", "Definida em", "Usada em"], rows) + [""]
    if undeclared:
        L += ["## Usadas no codigo e nao declaradas", "", ", ".join(f"`{k}`" for k in undeclared[:60]), ""]
    if envs:
        L += ["## Variaveis de ambiente", ""]
        L += [f"- `{k}` — " + ", ".join(f"`{f['fqn']}`" for f in v[:3]) for k, v in sorted(envs.items())] + [""]
    if unused:
        L += ["## Declaradas e sem uso aparente", "",
              "Podem ser lidas por frameworks (Spring Boot, Micronaut) sem referencia explicita.", "",
              ", ".join(f"`{k}`" for k in unused[:80]), ""]
    w.write(f"{cfg['docs_dir']}/CONFIG.md", "\n".join(L))


def emit_features(G: "Graph", D: dict, w: "Writer") -> None:
    cfg, S = G.cfg, G.syms
    feats = D["features"]
    L = ["# Funcionalidades (fatias verticais)", "", GEN_MARK, "",
         "Cada fatia parte de um entrypoint e percorre o codigo alcancavel: arquivos, camadas, "
         "tabelas, topicos, configuracao e testes. E o material de partida para planejar uma alteracao.", ""]
    rows = [[f"`{f['name']}`", ", ".join(f["entries"][:2]) + ("..." if len(f["entries"]) > 2 else ""),
             len(f["files"]), ", ".join(f["layers"][:4]) or "-", ", ".join(f"`{t}`" for t in f["tables"][:3]) or "-",
             len(f["tests"])] for f in feats]
    L += md_table(["Fatia", "Entradas", "Arquivos", "Camadas", "Tabelas", "Testes"], rows, "llrllr") + [""]
    for f in feats:
        L += [f"## {f['name']}", "", f"`{f['fqn']}` — `{f['at']}` — modulo `{f['module']}`", "",
              "Entradas: " + ", ".join(f"`{e}`" for e in f["entries"]), ""]
        L.append(f"Alcanca {f['symbols']} simbolos em {len(f['files'])} arquivos" +
                 (f", modulos {', '.join(f['modules'])}" if len(f["modules"]) > 1 else "") + ".")
        if f["tables"]:
            L.append("Tabelas: " + ", ".join(f"`{t}`" for t in f["tables"]))
        if f["topics"]:
            L.append("Topicos: " + ", ".join(f"`{t}`" for t in f["topics"]))
        if f["urls"]:
            L.append("Externo: " + ", ".join(f"`{u}`" for u in f["urls"][:5]))
        if f["config"]:
            L.append("Configuracao: " + ", ".join(f"`{c}`" for c in f["config"][:10]))
        L += ["", "Arquivos:", ""] + [f"- `{p}`" for p in f["files"][:25]]
        if len(f["files"]) > 25:
            L.append(f"- ... +{len(f['files']) - 25}")
        if f["tests"]:
            L += ["", "Testes que cobrem:", ""] + [f"- `{p}`" for p in f["tests"][:10]]
        else:
            L += ["", "**Sem teste alcancando esta fatia.**"]
        L.append("")
    if not feats:
        L.append("Nenhum entrypoint detectado, entao nao ha fatias.")
    w.write(f"{cfg['docs_dir']}/FEATURES.md", "\n".join(L))


def emit_conventions(G: "Graph", D: dict, w: "Writer") -> None:
    cfg, P = G.cfg, G.P
    c = D["conv"]
    L = ["# Convencoes do projeto", "", GEN_MARK, "",
         "Detectadas a partir do codigo existente. Siga-as ao escrever codigo novo.", "",
         f"- Linguagens: " + ", ".join(f"{k or 'outros'}={v}" for k, v in c["langs"].items()),
         f"- Organizacao de pacotes: {c['package_style']}",
         f"- Injecao de dependencia: {c['di']}",
         f"- Testes: " + (", ".join(c["test_libs"]) or "nenhuma biblioteca detectada") + f"; razao funcoes de teste/producao {c['test_ratio']}",
         f"- Log: " + (", ".join(c["log_libs"]) or "nao detectado"),
         f"- Tamanho medio: {c['avg_file_loc']} linhas por arquivo, {c['avg_fun_loc']} por funcao",
         f"- Funcoes suspend: {c['suspend']}",
         ""]
    if c["profiles"]:
        L += [f"- Perfis de configuracao: " + ", ".join(c["profiles"]), ""]
    if c["suffixes"]:
        L += ["## Sufixos de nome mais usados", "",
              ", ".join(f"`*{s}` ({n})" for s, n in c["suffixes"]), ""]
    if c["exceptions"]:
        L += ["## Excecoes do dominio", "", ", ".join(f"`{e}`" for e in c["exceptions"]), ""]
    ex = D.get("examples", {})
    if ex:
        L += ["## Exemplos canonicos por camada", "",
              "Use como modelo ao criar um componente novo da mesma camada.", ""]
        for layer, items in sorted(ex.items()):
            L.append(f"- **{layer}**: " + ", ".join(f"`{f}` (`{a}`)" for f, a in items[:3]))
        L.append("")
    w.write(f"{cfg['docs_dir']}/CONVENTIONS.md", "\n".join(L))


def emit_tests_doc(G: "Graph", D: dict, w: "Writer") -> None:
    cfg, S = G.cfg, G.syms
    cov = D["cov"]["cov"]
    L = ["# Cobertura estrutural de testes", "", GEN_MARK, "",
         "Quais testes alcancam cada tipo pelo grafo de chamadas. Nao e cobertura de linhas: "
         "indica se existe caminho de teste ate o codigo.", ""]
    types = [s for s in S if s["is_type"] and not s["test"] and s["owner"] < 0 and s["layer"] not in ("dto", "other")]
    covered = [s for s in types if cov.get(s["id"])]
    naked = [s for s in types if not cov.get(s["id"])]
    L += [f"- {len(covered)} de {len(types)} tipos relevantes alcancados por algum teste.", ""]
    if covered:
        L += ["## Cobertos", ""]
        rows = [[f"`{s['fqn']}`", s["layer"], len(cov[s["id"]]),
                 ", ".join(sorted({S[t]['file'].rsplit('/', 1)[-1] for t in cov[s['id']]})[:3])]
                for s in sorted(covered, key=lambda s: -len(cov[s["id"]]))[:40]]
        L += md_table(["Tipo", "Camada", "Testes", "Arquivos de teste"], rows, "llrl") + [""]
    if naked:
        L += ["## Sem teste alcancando", ""]
        rows = [[f"`{s['fqn']}`", s["layer"], s["loc"], loc_(s)] for s in
                sorted(naked, key=lambda s: -s["loc"])[:40]]
        L += md_table(["Tipo", "Camada", "Linhas", "Local"], rows, "llrl") + [""]
    w.write(f"{cfg['docs_dir']}/TESTS.md", "\n".join(L))


def emit_churn(G: "Graph", D: dict, w: "Writer") -> None:
    cfg = G.cfg
    ch = D.get("churn") or {}
    if not ch:
        return
    known = {p: v for p, v in ch.items() if p in G.files}
    L = ["# Historico (git)", "", GEN_MARK, "",
         "Arquivos mais alterados nos ultimos 12 meses. Alta rotatividade com alta complexidade "
         "costuma indicar onde uma mudanca da mais trabalho.", ""]
    rows = []
    for p, v in sorted(known.items(), key=lambda kv: -kv[1]["commits"])[:30]:
        last = time.strftime("%Y-%m-%d", time.localtime(v["last"])) if v["last"] else "-"
        rows.append([f"`{p}`", v["commits"], last, len(v["authors"]),
                     ", ".join(a for a, _ in v["authors"].most_common(2))])
    L += md_table(["Arquivo", "Commits", "Ultima alteracao", "Autores", "Principais"], rows, "lrlrl") + [""]
    stale = sorted((v["last"], p) for p, v in known.items() if v["last"])[:10]
    if stale:
        L += ["## Sem alteracao ha mais tempo", ""]
        L += [f"- `{p}` — {time.strftime('%Y-%m-%d', time.localtime(t))}" for t, p in stale] + [""]
    w.write(f"{cfg['docs_dir']}/HISTORY.md", "\n".join(L))


def canonical_examples(G: "Graph", D: dict) -> dict:
    """Melhor exemplo por camada: bem coberto por teste, tamanho tipico, documentado."""
    S, cov = G.syms, D["cov"]["cov"]
    out: dict[str, list] = defaultdict(list)
    for s in S:
        if not s["is_type"] or s["test"] or s["owner"] >= 0 or s["layer"] in ("other", "test"):
            continue
        score = (2 if cov.get(s["id"]) else 0) + (1 if s["doc"] else 0) + (1 if 15 <= s["loc"] <= 120 else 0) \
            + min(2, len(G.tfin_get(s["id"])) / 3)
        out[s["layer"]].append((round(score, 2), s["fqn"], loc_(s).strip("`")))
    return {k: [(f, a) for _, f, a in sorted(v, reverse=True)[:3]] for k, v in out.items()}


def safe(label: str, fn, default):
    """Nenhuma analise isolada pode derrubar a indexacao de um projeto real."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        warn(f"analise '{label}' falhou ({type(e).__name__}: {e}); seguindo sem ela.")
        return default


def discover(G: "Graph", A: dict, quiet: bool = False) -> dict:
    res = safe("recursos", lambda: scan_resources(G.P, G), {"tables": {}, "config": {}, "profiles": []})
    facts = safe("fatos do codigo", lambda: scan_code_facts(G, res)["facts"], [])
    safe("arestas de topico", lambda: topic_edges(G, facts), None)
    wiring = safe("wiring spring", lambda: spring_wiring(G), {"beans": [], "conditions": [], "transactions": [], "caches": [], "resilience": []})
    safe("arestas de bean", lambda: bean_edges(G, wiring), None)
    jpa = safe("modelo jpa", lambda: jpa_model(G, res), [])
    safe("arestas jpa", lambda: jpa_edges(G, jpa), None)
    xml = safe("xml (mybatis/liquibase)", lambda: scan_xml_resources(G.P, res, G), {"mybatis": [], "liquibase": []})
    android = safe("android", lambda: scan_android(G.P, G), [])
    for t in res["tables"].values():
        for f in t["used_by"]:
            if f.get("sym", -1) >= 0 and f not in facts:
                facts.append(f)
    cov = safe("cobertura", lambda: build_coverage(G), {"cov": {}, "tests": []})
    feats = safe("fatias", lambda: build_features(G, facts, cov["cov"]), [])
    conv = safe("convencoes", lambda: detect_conventions(G, res), {"package_style": "?", "di": "?", "test_libs": [],
                                                                    "log_libs": [], "suffixes": [], "avg_file_loc": 0,
                                                                    "avg_fun_loc": 0, "test_ratio": 0, "exceptions": [],
                                                                    "profiles": [], "langs": {}, "suspend": 0, "kt_files": 0})
    D = {"res": res, "facts": facts, "cov": cov, "features": feats, "conv": conv, "wiring": wiring,
         "jpa": jpa, "xml": xml, "android": android,
         "churn": safe("git churn", lambda: git_churn(G.P["root"], quiet=quiet), {})}
    D["examples"] = safe("exemplos", lambda: canonical_examples(G, D), {})
    return D


def emit_discovery(G: "Graph", A: dict, D: dict, w: "Writer") -> None:
    S, cfg = G.syms, G.cfg
    sd = cfg["state_dir"]
    write_jsonl(w, f"{sd}/facts.jsonl", D["facts"])
    write_jsonl(w, f"{sd}/features.jsonl", D["features"])
    write_jsonl(w, f"{sd}/tables.jsonl", (
        {"name": n, "columns": t["columns"], "ddl": t["ddl"], "ops": sorted(t["ops"]),
         "used_by": sorted({f["fqn"] for f in t["used_by"]})} for n, t in sorted(D["res"]["tables"].items())))
    write_jsonl(w, f"{sd}/config.jsonl", (
        {"key": k, "files": v["files"], "values": v["values"], "used_by": sorted({f["fqn"] for f in v["used_by"]})}
        for k, v in sorted(D["res"]["config"].items())))
    write_jsonl(w, f"{sd}/coverage.jsonl", (
        {"sym": i, "fqn": S[i]["fqn"], "file": S[i]["file"], "tests": sorted({S[t]["file"] for t in ts})}
        for i, ts in sorted(D["cov"]["cov"].items()) if ts))
    w.write(f"{sd}/conventions.json", json.dumps({**D["conv"], "examples": D["examples"]},
                                                 ensure_ascii=False, indent=1, sort_keys=True, default=list) + "\n")
    emit_data(G, D, w)
    emit_integrations(G, D, w)
    emit_config(G, D, w)
    emit_features(G, D, w)
    emit_conventions(G, D, w)
    emit_tests_doc(G, D, w)
    emit_churn(G, D, w)


# =========================================================================== #
# Consultas do discovery e planejamento de alteracao
# =========================================================================== #
def _load_rows(st: "Store", name: str) -> list:
    return list(st._lines(name))


def store_extras(st: "Store") -> None:
    if getattr(st, "_extras", False):
        return
    st._extras = True
    st.facts = _load_rows(st, "facts.jsonl")
    st.features = _load_rows(st, "features.jsonl")
    st.tables = {r["name"]: r for r in _load_rows(st, "tables.jsonl")}
    st.config = {r["key"]: r for r in _load_rows(st, "config.jsonl")}
    st.coverage = {r["sym"]: r for r in _load_rows(st, "coverage.jsonl")}
    try:
        st.conventions = json.loads((st.dir / "conventions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st.conventions = {}


def cmd_table(st: "Store", a) -> None:
    store_extras(st)
    if not a.terms:
        if a.json:
            out_json(list(st.tables.values()))
            return
        print(f"{len(st.tables)} tabela(s):\n")
        for n, t in sorted(st.tables.items()):
            print(f"  {n:34} {len(t['used_by']):>3} simbolos  {', '.join(t['ops']) or '-'}")
        return
    term = a.terms[0].lower()
    hits = {n: t for n, t in st.tables.items() if term in n}
    if not hits:
        raise SystemExit(f"Tabela nao encontrada: {term}")
    if a.json:
        out_json(list(hits.values()))
        return
    for n, t in sorted(hits.items()):
        print(f"\n=== {n} ===")
        if t["columns"]:
            print("  colunas: " + ", ".join(t["columns"]))
        for p, op in t["ddl"][:6]:
            print(f"  ddl: {p} ({op})")
        print("  operacoes: " + (", ".join(t["ops"]) or "-"))
        print("  acessado por:")
        for f in st.facts:
            if f["kind"] == "table" and f["value"] == n:
                print(f"    [{f['role']}] {f['fqn']}  {f['file']}:{f['line']}")


def cmd_config(st: "Store", a) -> None:
    store_extras(st)
    rows = list(st.config.values())
    if a.terms:
        t = a.terms[0].lower()
        rows = [r for r in rows if t in r["key"].lower()]
    if a.json:
        out_json(rows[:a.limit])
        return
    print(f"{len(rows)} chave(s):\n")
    for r in rows[:a.limit]:
        print(f"  {r['key']}")
        if r["values"]:
            print(f"      valor: {', '.join(r['values'][:3])}")
        if r["files"]:
            print(f"      definida: {', '.join(r['files'][:3])}")
        if r["used_by"]:
            print(f"      usada:    {', '.join(r['used_by'][:3])}")


def cmd_topic(st: "Store", a) -> None:
    store_extras(st)
    rows: dict[str, list] = defaultdict(list)
    for f in st.facts:
        if f["kind"] in ("topic", "url", "service"):
            if not a.terms or a.terms[0].lower() in f["value"].lower():
                rows[f"{f['kind']}:{f['value']}"].append(f)
    if a.json:
        out_json({k: v for k, v in rows.items()})
        return
    for k, v in sorted(rows.items())[:a.limit]:
        kind, val = k.split(":", 1)
        print(f"\n[{kind}] {val}")
        for f in v[:8]:
            print(f"    {f['role']}: {f['fqn']}  {f['file']}:{f['line']}" +
                  (f"  (payload: {f['payload']})" if f.get("payload") else ""))
    if not rows:
        print("Nenhuma integracao encontrada.")


def cmd_tests(st: "Store", a) -> None:
    store_extras(st)
    i = st.need(a.terms[0])
    ids = [i] + st.children.get(i, [])
    tests: set = set()
    for x in ids:
        r = st.coverage.get(x)
        if r:
            tests.update(r["tests"])
    if a.json:
        out_json({"fqn": st.label(i), "tests": sorted(tests)})
        return
    if tests:
        print(f"{len(tests)} arquivo(s) de teste alcancam {st.label(i)}:\n")
        for t in sorted(tests):
            print("  " + t)
        mod = st.syms[i].get("module", ".")
        mid = next((m["id"] for m in st.modules.values() if m["dir"] == mod), ":")
        print(f"\n  Rodar: {test_cmd_from_store(st, mid)}")
    else:
        print(f"Nenhum teste alcanca {st.label(i)} pelo grafo de chamadas.")


def test_cmd_from_store(st: "Store", mid: str) -> str:
    build = st.manifest["project"].get("build", "gradle")
    g = "./gradlew" if (st.root / "gradlew").exists() else ("./mvnw" if (st.root / "mvnw").exists() else ("mvn" if build == "maven" else "gradle"))
    if build == "maven":
        return f"{g} -q test" if mid == ":" else f"{g} -q -pl {mid.lstrip(':')} test"
    return f"{g} {'test' if mid == ':' else mid + ':test'} --console=plain -q"


def cmd_feature(st: "Store", a) -> None:
    store_extras(st)
    feats = st.features
    if a.terms:
        t = " ".join(a.terms).lower()
        feats = [f for f in feats if t in f["name"].lower() or t in f["fqn"].lower()
                 or any(t in e.lower() for e in f["entries"]) or any(t in x for x in f["tables"])]
    if a.json:
        out_json(feats[:a.limit])
        return
    if not feats:
        print("Nenhuma fatia encontrada.")
        return
    if not a.terms:
        print(f"{len(feats)} fatia(s):\n")
        for f in feats[:a.limit]:
            print(f"  {f['name']:28} {len(f['files']):>3} arquivos  {', '.join(f['layers'][:4])}")
            print(f"      entradas: {', '.join(f['entries'][:3])}")
        return
    for f in feats[:5]:
        print(f"\n=== {f['name']} ({f['at']}) ===")
        print("  entradas: " + ", ".join(f["entries"]))
        print(f"  alcance: {f['symbols']} simbolos, {len(f['files'])} arquivos, camadas {', '.join(f['layers'])}")
        for key, label in (("tables", "tabelas"), ("topics", "topicos"), ("urls", "externo"), ("config", "config")):
            if f[key]:
                print(f"  {label}: " + ", ".join(f[key][:8]))
        print("  arquivos:")
        for p in f["files"][:20]:
            print("    " + p)
        print("  testes: " + (", ".join(f["tests"][:6]) if f["tests"] else "NENHUM"))


def cmd_similar(st: "Store", a) -> None:
    store_extras(st)
    i = st.need(a.terms[0])
    base = st.syms[i]
    if not base.get("is_type") and base.get("owner", -1) >= 0:
        i = base["owner"]
    out = _similar_pairs(st, i)
    if a.json:
        out_json([{"score": sc, "fqn": st.label(j), "at": st.at(j), "layer": st.syms[j]["layer"]} for sc, j in out[:a.limit]])
        return
    print(f"Implementacoes analogas a {st.label(i)} (use como modelo):\n")
    for sc, j in out[:a.limit]:
        cov = st.coverage.get(j)
        print(f"  {sc:>4}  {sig_of(st.syms[j])}")
        print(f"        {st.at(j)}" + (f"  · coberto por {len(cov['tests'])} teste(s)" if cov else "  · sem teste"))
    if not out:
        print("  (nenhuma)")


def cmd_plan(st: "Store", a) -> None:
    """Roteiro de uma alteracao: contexto, fluxo, dependentes, efeitos, testes e modelos."""
    store_extras(st)
    term = " ".join(a.terms)
    low = term.lower()
    feats = [f for f in st.features if low in f["name"].lower() or low in f["fqn"].lower()
             or any(low in e.lower() for e in f["entries"])]
    i = None
    if not feats:
        i = st.need(term)
        sym_file = st.syms[i]["file"]
        feats = [f for f in st.features if sym_file in f["files"]]
    if i is None and feats:
        exact = [e for e in st.entries if low in e["label"].lower()]
        root = exact[0]["sym"] if exact else (feats[0]["entry_syms"][0] if feats[0]["entry_syms"] else None)
    else:
        root = i
    if root is None:
        raise SystemExit(f"Nao consegui situar '{term}'. Tente: query find {term}")
    rs = st.syms[root]
    tid = rs["owner"] if (not rs.get("is_type") and rs.get("owner", -1) >= 0) else root

    down = walk_edges(st, root, 4, "out", FOLLOW_KINDS)
    up = walk_edges(st, tid, 3, "in", DEP_KINDS)
    down_files = sorted({st.syms[x]["file"] for x, _, _, _, _, _ in down if not st.syms[x].get("test")})
    up_files = sorted({st.syms[x]["file"] for x, _, _, _, _, _ in up if not st.syms[x].get("test")} - set(down_files))
    for f in feats[:2]:
        for p in f["files"]:
            if p not in down_files and p not in up_files:
                down_files.append(p)
    down_files = sorted(set(down_files) - {st.syms[root]["file"]})
    impls = [e["s"] for e in st.inc.get(tid, []) if e["k"] in ("extends", "implements")]
    impls += [e["s"] for c in st.children.get(tid, []) for e in st.inc.get(c, []) if e["k"] == "overrides"]
    tests = sorted({st.syms[x]["file"] for x, _, _, _, _, _ in up if st.syms[x].get("test")}
                   | {t for f in feats[:2] for t in f["tests"]}
                   | set((st.coverage.get(tid) or {}).get("tests", [])))
    mods = sorted({st.syms[x]["module"] for x, _, _, _, _, _ in up} | {rs["module"]}
                  | {st.syms[x]["module"] for x, _, _, _, _, _ in down})
    mids = sorted({m["id"] for m in st.modules.values() if m["dir"] in mods})
    tables = sorted({t for f in feats for t in f["tables"]})
    cfgs = sorted({c for f in feats for c in f["config"]})
    topics = sorted({t for f in feats for t in f["topics"]})
    urls = sorted({u for f in feats for u in f["urls"]})
    models = [(sc, j) for sc, j in _similar_pairs(st, tid) if j != tid][:3]
    payload = {
        "alvo": st.label(root), "local": st.at(root), "fatias": [f["name"] for f in feats[:3]],
        "fluxo_abaixo": down_files, "quem_depende": up_files,
        "implementacoes": [st.label(x) for x in sorted(set(impls))],
        "tabelas": tables, "config": cfgs, "topicos": topics, "urls": urls,
        "testes": tests, "modulos": mids,
        "comandos_de_teste": [test_cmd_from_store(st, m) for m in mids] or [test_cmd_from_store(st, ":")],
        "modelos": [{"fqn": st.label(j), "at": st.at(j), "score": sc} for sc, j in models],
    }
    if a.json:
        out_json(payload)
        return
    bar = "=" * 72
    print(bar)
    print(f"PLANO DE ALTERACAO — {payload['alvo']}")
    print(bar)
    print(f"\n1. Ponto de partida\n   {sig_of(rs)}\n   {payload['local']}  ·  camada {rs.get('layer', '-')}  ·  modulo {rs.get('module', '.')}")
    if rs.get("doc"):
        print(f"   {rs['doc']}")
    if feats:
        print("\n2. Fatias que passam por aqui")
        for f in feats[:3]:
            print(f"   - {f['name']}: {', '.join(f['entries'][:3])}")
            print(f"     camadas {', '.join(f['layers'])}; {len(f['files'])} arquivos; {len(f['tests'])} teste(s)")
    print(f"\n3. Fluxo abaixo — o que este codigo aciona ({len(down_files)} arquivos)")
    for p in down_files[:20]:
        print("   " + p)
    if len(down_files) > 20:
        print(f"   ... +{len(down_files) - 20}")
    print(f"\n4. Quem depende — quebra se a assinatura mudar ({len(up_files)} arquivos)")
    for p in up_files[:20] or ["   (ninguem no indice)"][:0]:
        print("   " + p)
    if not up_files:
        print("   (ninguem no indice)")
    step = [5]

    def head(txt: str) -> None:
        print(f"\n{step[0]}. {txt}")
        step[0] += 1
    if impls:
        head(f"Implementacoes a ajustar em conjunto ({len(set(impls))})")
        for x in sorted(set(impls))[:10]:
            print(f"   {st.label(x)}  {st.at(x)}")
    head("Efeitos colaterais a conferir")
    any_side = False
    for label, vals in (("tabelas", tables), ("topicos", topics), ("externo", urls), ("config", cfgs)):
        if vals:
            any_side = True
            print(f"   {label:9} " + ", ".join(vals[:10]))
    if not any_side:
        print("   (nenhum recurso externo detectado nesta fatia)")
    head("Testes")
    if tests:
        for t in tests[:12]:
            print("   " + t)
    else:
        print("   NENHUM teste alcanca este codigo — escreva um antes de mudar.")
    head("Comandos")
    for c in payload["comandos_de_teste"][:4]:
        print("   " + c)
    print(f"   python {script_rel(st.root)}   # reindexar ao terminar")
    if models:
        head("Modelos analogos (mesmo padrao da casa)")
        for sc, j in models:
            cov = st.coverage.get(j)
            print(f"   {st.label(j)}  {st.at(j)}" + (f"  · {len(cov['tests'])} teste(s)" if cov else ""))
    print(bar)


def _similar_pairs(st: "Store", i: int) -> list:
    base = st.syms.get(i)
    if not base:
        return []
    kids = {st.syms[c]["name"] for c in st.children.get(i, [])}
    calls = {st.syms[e["d"]]["name"] for c in [i] + st.children.get(i, []) for e in st.out.get(c, [])}
    sup = set(base.get("supers_fq", [])) | set(base.get("ext_supers", []))
    out = []
    for j, s in st.syms.items():
        if j == i or not s.get("is_type") or s.get("owner", -1) >= 0 or bool(s.get("test")) != bool(base.get("test")):
            continue
        s_sup = set(s.get("supers_fq", [])) | set(s.get("ext_supers", []))
        if s.get("layer") != base.get("layer") and not (sup & s_sup):
            continue
        s_kids = {st.syms[c]["name"] for c in st.children.get(j, [])}
        s_calls = {st.syms[e["d"]]["name"] for c in [j] + st.children.get(j, []) for e in st.out.get(c, [])}
        def jac(x, y):
            return len(x & y) / len(x | y) if (x or y) else 0.0
        score = 2 * jac(sup, s_sup) + 1.2 * jac(kids, s_kids) + jac(calls, s_calls) + (0.4 if s.get("layer") == base.get("layer") else 0)
        if score > 0.35:
            out.append((round(score, 2), j))
    out.sort(reverse=True)
    return out


def cmd_churn(st: "Store", a) -> None:
    ch = git_churn(st.root)
    rows = sorted(((v["commits"], p, v) for p, v in ch.items() if p in st.files), reverse=True)
    if a.json:
        out_json([{"file": p, "commits": n, "last": v["last"], "authors": list(v["authors"])} for n, p, v in rows[:a.limit]])
        return
    if not rows:
        print("Sem historico git disponivel.")
        return
    print(f"{len(rows)} arquivo(s) com alteracoes nos ultimos 12 meses:\n")
    for n, p, v in rows[:a.limit]:
        last = time.strftime("%Y-%m-%d", time.localtime(v["last"])) if v["last"] else "-"
        print(f"  {n:>4} commits  {last}  {p}")


def cmd_why(st: "Store", a) -> None:
    """Por que este simbolo existe: quem o alcanca desde um entrypoint."""
    i = st.need(a.terms[0])
    paths = []
    entries = {e["sym"] for e in st.entries}
    seeds = [i] + st.children.get(i, [])
    prev: dict[int, tuple] = {x: None for x in seeds}
    q = deque(seeds)
    reached = []
    while q and len(reached) < 6:
        cur = q.popleft()
        if cur in entries and cur != i:
            reached.append(cur)
            continue
        for e in st.inc.get(cur, []):
            if (e["k"] not in DEP_KINDS and e["k"] != "implemented_by") or e["s"] in prev:
                continue
            prev[e["s"]] = (cur, e["k"], e.get("l", 0))
            q.append(e["s"])
    for r in reached:
        chain, cur = [], r
        while cur is not None:
            p = prev[cur]
            chain.append((cur, p[2] if p else 0))
            cur = p[0] if p else None
        paths.append(chain)
    if a.json:
        out_json({"fqn": st.label(i), "paths": [
            [{"fqn": st.label(x), "at": st.at(x),
              "evidence": f"{st.syms[x]['file']}:{ln}" if ln else st.at(x)} for x, ln in p]
            for p in paths]})
        return
    if not paths:
        print(f"{st.label(i)} nao e alcancado por nenhum entrypoint conhecido.")
        return
    print(f"Caminhos de entrada ate {st.label(i)}:\n")
    for p in paths:
        labels = [f"{st.syms[x]['name']}" for x, _ in p]
        ent = next((e["label"] for e in st.entries if e["sym"] == p[0][0]), st.label(p[0][0]))
        print(f"  {ent}\n    " + " -> ".join(labels))
        for x, ln in p[:-1]:
            print(f"    chamada em {st.syms[x]['file']}:{ln}" if ln else f"    {st.at(x)}")
        print(f"    origem: {st.at(p[0][0])}")


def cmd_conventions(st: "Store", a) -> None:
    store_extras(st)
    c = st.conventions
    if a.json:
        out_json(c)
        return
    if not c:
        print("Sem convencoes indexadas.")
        return
    for k in ("package_style", "di", "avg_file_loc", "avg_fun_loc", "test_ratio", "suspend"):
        if k in c:
            print(f"  {k:16} {c[k]}")
    for k in ("test_libs", "log_libs", "exceptions", "profiles"):
        if c.get(k):
            print(f"  {k:16} {', '.join(map(str, c[k]))}")
    if c.get("suffixes"):
        print("  sufixos         " + ", ".join(f"*{s} ({n})" for s, n in c["suffixes"][:8]))
    if c.get("examples"):
        print("\n  Exemplos canonicos:")
        for layer, items in sorted(c["examples"].items()):
            for fqn, at in items[:2]:
                print(f"    {layer:12} {fqn}  ({at})")


# =========================================================================== #
# Camada 2 de analise: alcancabilidade, clones, acoplamento historico,
# risco, glossario, superficie de API e diferencas entre execucoes.
# =========================================================================== #
REACH_KINDS = ("calls", "instantiates", "injects", "reads", "writes", "uses")
STOP_WORDS = {"the", "and", "for", "with", "from", "into", "impl", "abstract", "base", "default", "simple",
              "new", "old", "test", "tests", "util", "utils", "helper", "common", "core", "main", "api"}
LAYER_SUFFIX = {"Controller", "Service", "Repository", "Dao", "Dto", "DTO", "Mapper", "Config", "Configuration",
                "Client", "Job", "Listener", "Entity", "Exception", "Request", "Response", "Factory", "Builder",
                "Handler", "Provider", "Manager", "Validator", "Converter", "Adapter", "Gateway", "Impl",
                "Test", "Spec", "Event", "Command", "Query", "Model", "Properties", "Module", "Worker"}


def reachability(G: "Graph") -> dict:
    """Distancia de cada simbolo ate o entrypoint mais proximo."""
    S = G.syms
    adj: dict[int, list] = defaultdict(list)
    for (a, b, k), (ln, c) in G.edges.items():
        if k in REACH_KINDS and c >= 0.5:
            adj[a].append(b)
        elif k == "overrides":
            adj[b].append(a)
        elif k in ("extends", "implements"):
            adj[b].append(a)
    owner_of = {s["id"]: s["owner"] for s in S}
    seeds = [e["sym"] for e in G.entries]
    depth: dict[int, int] = {}
    q = deque()
    for x in seeds:
        depth[x] = 0
        q.append(x)
        ow = owner_of.get(x, -1)
        if ow >= 0 and ow not in depth:
            depth[ow] = 0
            q.append(ow)
    while q:
        cur = q.popleft()
        d = depth[cur]
        nxt_list = list(adj.get(cur, ()))
        ow = owner_of.get(cur, -1)
        if ow >= 0:
            nxt_list.append(ow)
        for nxt in nxt_list:
            if nxt not in depth:
                depth[nxt] = d + 1
                q.append(nxt)
    unreachable = [s for s in S if not s["test"] and s["id"] not in depth
                   and s["kind"] in ("class", "interface", "object", "data class", "abstract class", "enum", "fun")
                   and s["vis"] != "private" and not s["annots"]]
    return {"depth": depth, "unreachable": unreachable,
            "reached": len(depth), "total": sum(1 for s in S if not s["test"])}


def find_clones(G: "Graph") -> list[dict]:
    """Funcoes com corpo estruturalmente identico (candidatas a extrair)."""
    by_fp: dict[str, list] = defaultdict(list)
    for s in G.syms:
        if s["kind"] in ("fun", "constructor") and s["fp"] and s["ntok"] >= 40:
            by_fp[s["fp"]].append(s)
    out = []
    for fp, group in by_fp.items():
        files = {s["file"] for s in group}
        if len(group) < 2 or (len(files) == 1 and len(group) < 3):
            continue
        out.append({"fp": fp, "tokens": group[0]["ntok"], "count": len(group),
                    "files": sorted(files), "test": all(s["test"] for s in group),
                    "members": [{"fqn": s["fqn"], "at": f"{s['file']}:{s['line']}", "loc": s["loc"]} for s in group[:12]]})
    out.sort(key=lambda c: (-c["count"], -c["tokens"]))
    return out[:60]


def cochange(churn_raw: dict, root: Path, files: set, months: int = 12, max_files: int = 25,
             quiet: bool = False) -> dict:
    """Pares de arquivos que costumam mudar no mesmo commit."""
    if not quiet:
        print("  analisando acoplamento historico (cochange)...", file=sys.stderr)
    try:
        out = subprocess.run(["git", "-C", str(root), "log", f"--since={months}.months", "--no-merges", "-n4000",
                              "--pretty=format:@", "--name-only"],
                             capture_output=True, text=True, timeout=120, check=True, errors="replace").stdout
    except Exception:  # noqa: BLE001
        return {}
    prefix = git_name_only_prefix(root)
    pairs: Counter = Counter()
    commits: Counter = Counter()
    cur: list[str] = []
    def flush(group: list) -> None:
        g = sorted({p for p in group if p in files})
        if 1 < len(g) <= max_files:
            for i in range(len(g)):
                commits[g[i]] += 1
                for j in range(i + 1, len(g)):
                    pairs[(g[i], g[j])] += 1
        elif len(g) == 1:
            commits[g[0]] += 1
    for line in out.splitlines():
        if line.startswith("@"):
            flush(cur)
            cur = []
        elif line.strip():
            path = line.strip()
            if prefix:
                if not path.startswith(prefix):
                    continue
                path = path[len(prefix):]
            cur.append(path)
    flush(cur)
    res: dict[str, list] = defaultdict(list)
    for (a, b), n in pairs.items():
        if n < 2:
            continue
        conf_a = n / max(1, commits[a])
        conf_b = n / max(1, commits[b])
        res[a].append({"file": b, "together": n, "conf": round(conf_a, 2)})
        res[b].append({"file": a, "together": n, "conf": round(conf_b, 2)})
    for k in res:
        res[k] = sorted(res[k], key=lambda x: (-x["together"], -x["conf"]))[:8]
    return dict(res)


def risk_scores(G: "Graph", A: dict, D: dict) -> list[dict]:
    """Risco por arquivo: complexidade, tamanho, acoplamento, churn e ausencia de teste."""
    S, cov = G.syms, D["cov"]["cov"]
    churn = D.get("churn") or {}
    rows = []
    max_churn = max([v["commits"] for p, v in churn.items() if p in G.files] or [1])
    fin = A.get("tfin", {})
    for path, f in G.files.items():
        if f["test"]:
            continue
        ids = f["ids"]
        cc = max([S[i]["cc"] for i in ids] or [0])
        loc = f["loc"]
        coupling = sum(len(fin.get(i, ())) for i in ids if S[i]["is_type"])
        ch = churn.get(path, {}).get("commits", 0)
        covered = any(cov.get(i) for i in ids)
        score = (min(cc, 40) / 40 * 30 + min(loc, 800) / 800 * 20 + min(coupling, 30) / 30 * 20
                 + (ch / max_churn) * 20 + (0 if covered else 10))
        rows.append({"file": path, "score": round(score, 1), "cc": cc, "loc": loc, "fan_in": coupling,
                     "commits": ch, "tested": covered, "module": f["module"]})
    rows.sort(key=lambda r: -r["score"])
    return rows


def api_surface(G: "Graph") -> dict:
    """O que cada modulo expoe e o que e realmente consumido de fora."""
    S = G.syms
    entry_types = {S[e["sym"]]["owner"] if S[e["sym"]]["owner"] >= 0 else e["sym"] for e in G.entries}
    used_outside: dict[int, set] = defaultdict(set)
    for (a, b, k), (ln, c) in G.edges.items():
        if k in DEP_KINDS and S[a]["module"] != S[b]["module"] and not S[a]["test"]:
            used_outside[b].add(S[a]["module"])
    out: dict[str, dict] = {}
    for d, m in G.P["mods"].items():
        exported = [s for s in S if s["module"] == d and not s["test"] and s["vis"] == "public"
                    and s["is_type"] and s["owner"] < 0]
        if not exported:
            continue
        used = [s for s in exported if used_outside.get(s["id"])]
        unused = [s for s in exported if not used_outside.get(s["id"]) and s["id"] not in entry_types
                  and not any(used_outside.get(c["id"]) for c in S if c["owner"] == s["id"])]
        out[m["id"]] = {
            "exported": len(exported), "consumed": len(used),
            "consumers": sorted({x for s in used for x in used_outside[s["id"]]}),
            "public_unused": [{"fqn": s["fqn"], "at": f"{s['file']}:{s['line']}", "layer": s["layer"]} for s in unused[:40]],
            "hot": [{"fqn": s["fqn"], "by": sorted(used_outside[s["id"]])} for s in
                    sorted(used, key=lambda s: -len(used_outside[s["id"]]))[:10]],
        }
    return out


def glossary(G: "Graph") -> list[tuple]:
    """Vocabulario do dominio: termos recorrentes nos nomes de tipos."""
    terms: Counter = Counter()
    where: dict[str, set] = defaultdict(set)
    for s in G.syms:
        if not s["is_type"] or s["test"]:
            continue
        parts = re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*", s["name"])
        for p in parts:
            if p in LAYER_SUFFIX or p.lower() in STOP_WORDS or len(p) < 4:
                continue
            terms[p] += 1
            where[p].add(s["fqn"])
    return [(t, n, sorted(where[t])[:6]) for t, n in terms.most_common(40) if n > 1]


def sym_hash(s: dict) -> str:
    base = f"{s['kind']}|{s['sig']}|{s['vis']}|{sorted(s['mods'])}|{sorted(s['annots'])}|{s['ret']}|{s.get('fp', '')}"
    return hashlib.sha1(base.encode("utf-8", "replace")).hexdigest()[:12]


def diff_snapshot(G: "Graph", root: Path, cfg: dict, write: bool) -> dict:
    """Compara com a execucao anterior: o que nasceu, sumiu ou mudou de forma."""
    path = root / cfg["state_dir"] / "snapshot.json"
    cur = {s["fqn"] + ("#" + s["sig"] if s["kind"] in ("fun", "constructor") else ""):
           [sym_hash(s), s["file"], s["line"]] for s in G.syms if not s["test"]}
    prev = {}
    try:
        prev = json.loads(path.read_text(encoding="utf-8")).get("syms", {})
    except (OSError, ValueError):
        prev = {}
    added = sorted(set(cur) - set(prev))
    removed = sorted(set(prev) - set(cur))
    changed = sorted(k for k in set(cur) & set(prev) if cur[k][0] != prev[k][0])
    moved = sorted(k for k in set(cur) & set(prev) if cur[k][1] != prev[k][1])
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"at": int(time.time()), "syms": cur}, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
    # par adicionado+removido com mesmo FQN = assinatura alterada
    def fqn_of(k):
        return k.split("#", 1)[0]
    rem_by_fqn: dict = defaultdict(list)
    for k in removed:
        rem_by_fqn[fqn_of(k)].append(k)
    resigned, add2, rem2 = [], [], list(removed)
    for k in added:
        cand = rem_by_fqn.get(fqn_of(k))
        if cand:
            old = cand.pop(0)
            rem2.remove(old)
            resigned.append({"fqn": fqn_of(k), "de": old.split("#", 1)[-1] if "#" in old else "",
                             "para": k.split("#", 1)[-1] if "#" in k else "", "at": f"{cur[k][1]}:{cur[k][2]}"})
        else:
            add2.append(k)
    return {"first_run": not prev, "added": add2, "removed": rem2, "changed": changed,
            "resigned": resigned, "moved": [m for m in moved if m not in changed], "cur": cur}


def changed_impact(G: "Graph", diff: dict, limit: int = 40) -> list[dict]:
    """Para cada simbolo alterado, quem depende dele e quais testes o cobrem."""
    by_key = {}
    for s in G.syms:
        key = s["fqn"] + ("#" + s["sig"] if s["kind"] in ("fun", "constructor") else "")
        by_key[key] = s
    inc: dict[int, list] = defaultdict(list)
    for (a, b, k), (ln, c) in G.edges.items():
        if k in DEP_KINDS:
            inc[b].append(a)
    out = []
    for key in (diff["changed"] + [r["fqn"] + ("#" + r["para"] if r["para"] else "") for r in diff.get("resigned", [])] + diff["added"])[:limit]:
        s = by_key.get(key)
        if s is None:
            continue
        deps = sorted({G.syms[x]["file"] for x in inc.get(s["id"], []) if not G.syms[x]["test"]})
        tests = sorted({G.syms[x]["file"] for x in inc.get(s["id"], []) if G.syms[x]["test"]})
        out.append({"fqn": s["fqn"], "kind": s["kind"], "at": f"{s['file']}:{s['line']}",
                    "status": ("alterado" if key in diff["changed"]
                               else ("assinatura alterada" if any(r["fqn"] == s["fqn"] for r in diff.get("resigned", []))
                                     else "novo")),
                    "dependentes": deps[:12], "testes": tests[:6]})
    return out


# =========================================================================== #
# Docs e consultas da camada 2
# =========================================================================== #
def emit_changes(G: "Graph", D: dict, w: "Writer") -> None:
    cfg = G.cfg
    diff, items = D["diff"], D["changed_impact"]
    rel = f"{cfg['docs_dir']}/CHANGES.md"
    quiet_run = not diff["first_run"] and not any(
        diff[k] for k in ("added", "removed", "changed", "moved")) and not diff.get("resigned")
    if quiet_run and (w.root / rel).exists():
        w.written.add(rel)  # nada mudou: preserva o ultimo relatorio
        return
    L = ["# O que mudou desde a ultima indexacao", "", GEN_MARK, ""]
    if diff["first_run"]:
        L += ["Primeira execucao: nao ha comparacao. A partir da proxima, este arquivo mostra",
              "simbolos novos, removidos e com assinatura ou corpo alterado, com o impacto de cada um.", ""]
    else:
        L += [f"- {len(diff['added'])} novos, {len(diff['removed'])} removidos, {len(diff['changed'])} alterados, "
              f"{len(diff.get('resigned', []))} com assinatura alterada, {len(diff['moved'])} movidos de lugar.", ""]
        if diff.get("resigned"):
            L += ["## Assinaturas alteradas", "", "Quem chamava pode nao compilar mais.", ""]
            for r in diff["resigned"][:30]:
                L.append(f"- `{r['fqn']}`: `{r['de']}` → `{r['para']}` — `{r['at']}`")
            L.append("")
        if diff["removed"]:
            L += ["## Removidos", "", "Confira quem os usava antes de concluir a alteracao.", ""]
            L += [f"- `{k}`" for k in diff["removed"][:40]] + [""]
        if items:
            L += ["## Novos e alterados, com impacto", ""]
            for it in items:
                L.append(f"### {it['fqn']} ({it['status']})")
                L.append(f"`{it['at']}` — {it['kind']}")
                if it["dependentes"]:
                    L.append("Dependentes: " + ", ".join(f"`{p}`" for p in it["dependentes"]))
                L.append("Testes que tocam: " + (", ".join(f"`{p}`" for p in it["testes"]) if it["testes"] else "**nenhum**"))
                L.append("")
        if diff["moved"]:
            L += ["## Apenas mudaram de lugar", ""] + [f"- `{k}`" for k in diff["moved"][:30]] + [""]
    w.write(rel, "\n".join(L))


def emit_risk(G: "Graph", A: dict, D: dict, w: "Writer") -> None:
    cfg = G.cfg
    rows = D["risk"]
    unreach = D["reach"]["unreachable"]
    clones = D["clones"]
    L = ["# Risco e pontos de atencao", "", GEN_MARK, "",
         "Risco combina complexidade, tamanho, acoplamento, rotatividade no git e ausencia de teste. "
         "Serve para decidir onde ir com mais cuidado, nao para julgar o codigo.", "", "## Arquivos de maior risco", ""]
    L += md_table(["Arquivo", "Risco", "CC max", "Linhas", "Usado por", "Commits", "Testado"],
                  [[f"`{r['file']}`", r["score"], r["cc"], r["loc"], r["fan_in"], r["commits"],
                    "sim" if r["tested"] else "**nao**"] for r in rows[:25]], "lrrrrrl") + [""]
    if unreach:
        L += [f"## Nao alcancavel a partir de nenhum entrypoint ({len(unreach)})", "",
              "Pode ser API de biblioteca, codigo chamado por reflexao ou DI, ou codigo de fato orfao.", ""]
        L += md_table(["Simbolo", "Tipo", "Camada", "Linhas", "Local"],
                      [[f"`{s['fqn']}`", s["kind"], s["layer"], s["loc"], loc_(s)]
                       for s in sorted(unreach, key=lambda s: -s["loc"])[:40]], "lllrl") + [""]
    if clones:
        L += [f"## Codigo duplicado ({len(clones)} grupos)", "",
              "Funcoes com corpo estruturalmente identico. Em migracao costuma indicar padrao repetido "
              "que vale extrair antes de mudar.", ""]
        for c in clones[:15]:
            L.append(f"- {c['count']} copias (~{c['tokens']} tokens): " +
                     ", ".join(f"`{m['fqn']}` (`{m['at']}`)" for m in c["members"][:4]) +
                     (f" e mais {c['count'] - 4}" if c["count"] > 4 else ""))
        L.append("")
    w.write(f"{cfg['docs_dir']}/RISK.md", "\n".join(L))


def emit_surface(G: "Graph", D: dict, w: "Writer") -> None:
    cfg = G.cfg
    surf = D["surface"]
    L = ["# Superficie publica dos modulos", "", GEN_MARK, "",
         "O que cada modulo expoe e o que outros modulos realmente consomem. "
         "Publico sem consumidor externo pode virar `internal`/`private` e reduzir o acoplamento.", ""]
    L += md_table(["Modulo", "Tipos publicos", "Consumidos de fora", "Quem consome"],
                  [[f"`{k}`", v["exported"], v["consumed"], ", ".join(f"`{c}`" for c in v["consumers"]) or "-"]
                   for k, v in sorted(surf.items())], "lrrl") + [""]
    for mid, v in sorted(surf.items()):
        if not v["hot"] and not v["public_unused"]:
            continue
        L += [f"## `{mid}`", ""]
        if v["hot"]:
            L += ["Mais consumidos:", ""] + [f"- `{h['fqn']}` — por {', '.join(h['by'])}" for h in v["hot"]] + [""]
        if v["public_unused"]:
            L += [f"Publicos sem consumidor externo ({len(v['public_unused'])}):", ""]
            L += [f"- `{u['fqn']}` ({u['layer']}) — `{u['at']}`" for u in v["public_unused"][:25]] + [""]
    w.write(f"{cfg['docs_dir']}/SURFACE.md", "\n".join(L))


def emit_glossary(G: "Graph", D: dict, w: "Writer") -> None:
    cfg = G.cfg
    terms = D["glossary"]
    L = ["# Glossario do dominio", "", GEN_MARK, "",
         "Termos recorrentes nos nomes de tipos. Use este vocabulario ao nomear codigo novo.", ""]
    L += md_table(["Termo", "Ocorrencias", "Exemplos"],
                  [[f"`{t}`", n, ", ".join(f"`{x.rsplit('.', 1)[-1]}`" for x in ex[:4])] for t, n, ex in terms], "lrl")
    w.write(f"{cfg['docs_dir']}/GLOSSARY.md", "\n".join(L))


def emit_coupling(G: "Graph", D: dict, w: "Writer") -> None:
    cfg = G.cfg
    co = D.get("cochange") or {}
    if not co:
        return
    L = ["# Acoplamento historico", "", GEN_MARK, "",
         "Arquivos que costumam ser alterados no mesmo commit. Se voce mexeu em um, confira os outros: "
         "e o acoplamento que o grafo estatico nao enxerga.", ""]
    rows = []
    for a, partners in sorted(co.items(), key=lambda kv: -max(p["together"] for p in kv[1]))[:40]:
        rows.append([f"`{a}`", ", ".join(f"`{p['file'].rsplit('/', 1)[-1]}` ({p['together']}x, {int(p['conf'] * 100)}%)"
                                         for p in partners[:3])])
    L += md_table(["Arquivo", "Costuma mudar junto com"], rows)
    w.write(f"{cfg['docs_dir']}/COUPLING.md", "\n".join(L))


def deep_analysis(G: "Graph", A: dict, D: dict, root: Path, cfg: dict, write: bool, quiet: bool = False) -> None:
    D["reach"] = safe("alcancabilidade", lambda: reachability(G), {"depth": {}, "unreachable": [], "reached": 0, "total": 0})
    D["clones"] = safe("clones", lambda: find_clones(G), [])
    D["cochange"] = safe("acoplamento historico",
                          lambda: cochange(D.get("churn") or {}, root, set(G.files), max_files=25, quiet=quiet), {})
    D["risk"] = safe("risco", lambda: risk_scores(G, A, D), [])
    D["surface"] = safe("superficie", lambda: api_surface(G), {})
    D["glossary"] = safe("glossario", lambda: glossary(G), [])
    D["diff"] = safe("diferencas", lambda: diff_snapshot(G, root, cfg, write),
                     {"first_run": True, "added": [], "removed": [], "changed": [], "moved": [], "resigned": [], "cur": {}})
    D["changed_impact"] = safe("impacto das mudancas", lambda: changed_impact(G, D["diff"]), [])


def emit_deep(G: "Graph", A: dict, D: dict, w: "Writer") -> None:
    sd = G.cfg["state_dir"]
    S = G.syms
    write_jsonl(w, f"{sd}/risk.jsonl", D["risk"][:400])
    write_jsonl(w, f"{sd}/clones.jsonl", D["clones"])
    write_jsonl(w, f"{sd}/surface.jsonl", ({"module": k, **v} for k, v in sorted(D["surface"].items())))
    write_jsonl(w, f"{sd}/reach.jsonl", (
        {"sym": s["id"], "fqn": s["fqn"], "file": s["file"], "line": s["line"], "kind": s["kind"],
         "layer": s["layer"], "loc": s["loc"], "reachable": False}
        for s in sorted(D["reach"]["unreachable"], key=lambda x: -x["loc"])[:2000]))
    if D.get("cochange"):
        write_jsonl(w, f"{sd}/coupling.jsonl", ({"file": k, "partners": v} for k, v in sorted(D["cochange"].items())))
    quiet = not D["diff"]["first_run"] and not any(
        D["diff"][k] for k in ("added", "removed", "changed", "moved")) and not D["diff"].get("resigned")
    if quiet and (w.root / f"{sd}/changes.json").exists():
        w.written.add(f"{sd}/changes.json")
    else:
        w.write(f"{sd}/changes.json", json.dumps(
        {"first_run": D["diff"]["first_run"], "added": D["diff"]["added"][:500], "removed": D["diff"]["removed"][:500],
         "changed": D["diff"]["changed"][:500], "resigned": D["diff"].get("resigned", [])[:200],
         "moved": D["diff"]["moved"][:300], "impact": D["changed_impact"]},
            ensure_ascii=False, indent=1) + "\n")
    w.write(f"{sd}/glossary.json", json.dumps(
        [{"term": t, "count": n, "examples": ex} for t, n, ex in D["glossary"]], ensure_ascii=False, indent=1) + "\n")
    emit_changes(G, D, w)
    emit_risk(G, A, D, w)
    emit_surface(G, D, w)
    emit_glossary(G, D, w)
    emit_coupling(G, D, w)


# --------------------------------------------------------------------------- #
# Consultas da camada 2
# --------------------------------------------------------------------------- #
def store_deep(st: "Store") -> None:
    if getattr(st, "_deep", False):
        return
    st._deep = True
    st.risk = _load_rows(st, "risk.jsonl")
    st.clones = _load_rows(st, "clones.jsonl")
    st.surface = {r["module"]: r for r in _load_rows(st, "surface.jsonl")}
    st.unreachable = _load_rows(st, "reach.jsonl")
    st.coupling = {r["file"]: r["partners"] for r in _load_rows(st, "coupling.jsonl")}
    try:
        st.changes = json.loads((st.dir / "changes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st.changes = {"first_run": True, "added": [], "removed": [], "changed": [], "moved": [], "impact": []}
    try:
        st.glossary = json.loads((st.dir / "glossary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st.glossary = []


def cmd_changed(st: "Store", a) -> None:
    store_deep(st)
    c = st.changes
    if a.json:
        out_json(c)
        return
    if c.get("first_run"):
        print("Primeira indexacao registrada: ainda nao ha comparacao. Rode de novo apos alterar o codigo.")
        return
    print(f"{len(c['added'])} novos · {len(c['removed'])} removidos · {len(c['changed'])} alterados · "
          f"{len(c.get('resigned', []))} com assinatura alterada · {len(c['moved'])} movidos\n")
    for r in c.get("resigned", [])[:a.limit]:
        print(f"  [assinatura] {r['fqn']}\n      {r['de']}  ->  {r['para']}\n      {r['at']}")
    for it in c["impact"][:a.limit]:
        print(f"  [{it['status']}] {it['fqn']}  ({it['at']})")
        if it["dependentes"]:
            print("      dependentes: " + ", ".join(it["dependentes"][:4]))
        print("      testes: " + (", ".join(it["testes"][:3]) if it["testes"] else "NENHUM"))
    if c["removed"]:
        print("\n  Removidos:")
        for k in c["removed"][:a.limit]:
            print("    " + k)


def cmd_risk(st: "Store", a) -> None:
    store_deep(st)
    rows = st.risk
    if a.terms:
        t = a.terms[0].lower()
        rows = [r for r in rows if t in r["file"].lower() or t in r.get("module", "").lower()]
    if a.json:
        out_json(rows[:a.limit])
        return
    print(f"{'risco':>6}  {'cc':>4} {'linhas':>7} {'usos':>5} {'commits':>8}  arquivo")
    for r in rows[:a.limit]:
        flag = "" if r["tested"] else "  (sem teste)"
        print(f"{r['score']:>6}  {r['cc']:>4} {r['loc']:>7} {r['fan_in']:>5} {r['commits']:>8}  {r['file']}{flag}")


def cmd_clones(st: "Store", a) -> None:
    store_deep(st)
    rows = st.clones
    if a.terms:
        t = a.terms[0].lower()
        rows = [c for c in rows if any(t in m["fqn"].lower() for m in c["members"])]
    if a.json:
        out_json(rows[:a.limit])
        return
    if not rows:
        print("Nenhum grupo de codigo duplicado encontrado.")
        return
    for c in rows[:a.limit]:
        print(f"\n{c['count']} copias (~{c['tokens']} tokens):")
        for m in c["members"][:8]:
            print(f"    {m['fqn']}  {m['at']}")


def cmd_unreachable(st: "Store", a) -> None:
    store_deep(st)
    rows = st.unreachable
    if a.terms:
        t = a.terms[0].lower()
        rows = [r for r in rows if t in r["fqn"].lower() or t in r["file"].lower()]
    if a.json:
        out_json(rows[:a.limit])
        return
    print(f"{len(rows)} simbolo(s) sem caminho a partir de um entrypoint "
          "(pode ser DI, reflexao ou API externa — confirme):\n")
    for r in sorted(rows, key=lambda r: -r["loc"])[:a.limit]:
        print(f"  {r['kind']:14} {r['fqn']}\n      {r['file']}:{r['line']}  ({r['loc']} linhas, {r['layer']})")


def cmd_surface(st: "Store", a) -> None:
    store_deep(st)
    mods = st.surface
    if a.terms:
        mods = {k: v for k, v in mods.items() if a.terms[0] in k}
    if a.json:
        out_json(list(mods.values()))
        return
    for mid, v in sorted(mods.items()):
        print(f"\n{mid}: {v['exported']} tipos publicos, {v['consumed']} consumidos por {', '.join(v['consumers']) or 'ninguem'}")
        for h in v["hot"][:5]:
            print(f"    quente: {h['fqn']}  (por {', '.join(h['by'])})")
        if v["public_unused"]:
            print(f"    publicos sem consumidor externo ({len(v['public_unused'])}):")
            for u in v["public_unused"][:8]:
                print(f"      {u['fqn']}  {u['at']}")


def cmd_coupled(st: "Store", a) -> None:
    store_deep(st)
    if not st.coupling:
        print("Sem historico git suficiente para calcular acoplamento.")
        return
    if not a.terms:
        rows = sorted(st.coupling.items(), key=lambda kv: -max(p["together"] for p in kv[1]))
        if a.json:
            out_json([{"file": k, "partners": v} for k, v in rows[:a.limit]])
            return
        for k, v in rows[:a.limit]:
            print(f"  {k}")
            for p in v[:3]:
                print(f"      {p['file']}  ({p['together']}x, {int(p['conf'] * 100)}%)")
        return
    term = a.terms[0]
    hits = {k: v for k, v in st.coupling.items() if term in k}
    if a.json:
        out_json([{"file": k, "partners": v} for k, v in hits.items()])
        return
    if not hits:
        print(f"Nenhum acoplamento historico para '{term}'.")
        return
    for k, v in hits.items():
        print(f"\n{k} costuma mudar junto com:")
        for p in v:
            print(f"    {p['file']}  ({p['together']}x, {int(p['conf'] * 100)}% das vezes)")


def cmd_glossary(st: "Store", a) -> None:
    store_deep(st)
    rows = st.glossary
    if a.terms:
        t = a.terms[0].lower()
        rows = [r for r in rows if t in r["term"].lower()]
    if a.json:
        out_json(rows[:a.limit])
        return
    for r in rows[:a.limit]:
        print(f"  {r['term']:22} {r['count']:>3}  " + ", ".join(x.rsplit(".", 1)[-1] for x in r["examples"][:5]))


def cmd_accessors(st: "Store", a) -> None:
    """Quem le e quem escreve uma propriedade."""
    i = st.need(a.terms[0])
    ids = [i] + st.children.get(i, [])
    reads, writes = [], []
    for x in ids:
        for e in st.inc.get(x, []):
            if e["k"] == "reads":
                reads.append((e["s"], x, e.get("l", 0)))
            elif e["k"] == "writes":
                writes.append((e["s"], x, e.get("l", 0)))
    if a.json:
        out_json({"fqn": st.label(i),
                  "reads": [{"from": st.label(s), "prop": st.label(d), "at": f"{st.syms[s]['file']}:{ln}"} for s, d, ln in reads],
                  "writes": [{"from": st.label(s), "prop": st.label(d), "at": f"{st.syms[s]['file']}:{ln}"} for s, d, ln in writes]})
        return
    print(f"Acessos a {st.label(i)}:\n")
    for label, rows in (("escrita", writes), ("leitura", reads)):
        print(f"  [{label}] {len(rows)}")
        for s, d, ln in rows[:a.limit]:
            print(f"    {st.label(s)} → {st.syms[d]['name']}   {st.syms[s]['file']}:{ln}")


def cmd_branches(st: "Store", a) -> None:
    """Grafo de fluxo de execucao (if/when) de uma funcao — caminhos, nao so contagem de
    complexidade: mostra cada ramo (true/false/arm) e onde cada um termina (return/throw/exit),
    o que um numero de complexidade ciclomatica sozinho nao distingue."""
    i = st.need(a.terms[0])
    s = st.syms[i]
    fg = s.get("flow")
    if a.json:
        out_json({"fqn": st.label(i), "at": st.at(i), "flow": fg})
        return
    print(f"Fluxo de {st.label(i)}  ·  {st.at(i)}")
    if not fg:
        print("\n  Sem grafo de fluxo (funcao sem if/when, ou fora do escopo atual — so Kotlin).")
        return
    by_id = {n["id"]: n for n in fg["nodes"]}
    out = defaultdict(list)
    for e in fg["edges"]:
        out[e["src"]].append(e)
    print()
    for n in fg["nodes"]:
        lbl = f"  [{n['id']}] {n['kind']:9s} L{n['line']}" + (f"  {n['label']!r}" if n["label"] else "")
        print(lbl)
        for e in out.get(n["id"], []):
            dst = by_id[e["dst"]]
            print(f"        --{e['label']}--> [{dst['id']}] {dst['kind']}")


# =========================================================================== #
# Docs e consultas de runtime/persistencia
# =========================================================================== #
def emit_runtime(G: "Graph", D: dict, w: "Writer") -> None:
    cfg = G.cfg
    W = D["wiring"]
    L = ["# Comportamento em execucao", "", GEN_MARK, "",
         "Ligacoes e comportamentos declarados por anotacao que o grafo estatico nao mostra: "
         "beans, condicionais, transacoes, cache e resiliencia.", ""]
    if W["beans"]:
        L += ["## Beans declarados", "",
              "Quem, em tempo de execucao, satisfaz cada tipo. Trocar a implementacao passa por aqui.", ""]
        L += md_table(["Tipo", "Implementacao", "Declarado em", "Local"],
                      [[f"`{b['tipo']}`", ", ".join(f"`{i}`" for i in b["implementacao"]) or "-",
                        f"`{b['config']}`", f"`{b['at']}`"] for b in W["beans"][:60]]) + [""]
    if W["conditions"]:
        L += ["## Ativacao condicional", "",
              "Componentes que so existem sob certas propriedades ou perfis. Confirme o ambiente antes de assumir que o codigo roda.", ""]
        L += md_table(["Componente", "Condicao", "Valores", "Local"],
                      [[f"`{c['fqn']}`", f"@{c['anotacao']}", ", ".join(f"`{v}`" for v in c["valores"]) or "-", f"`{c['at']}`"]
                       for c in W["conditions"][:60]]) + [""]
    if W["transactions"]:
        L += ["## Limites transacionais", "",
              "Onde a transacao comeca. Alterar chamada dentro desses limites muda o escopo do commit ou rollback.", ""]
        L += md_table(["Alvo", "Escopo", "Argumentos", "Local"],
                      [[f"`{t['fqn']}`", t["escopo"], f"`{t['args']}`" if t["args"] else "-", f"`{t['at']}`"]
                       for t in W["transactions"][:60]]) + [""]
    if W["caches"]:
        L += ["## Cache", ""]
        L += md_table(["Alvo", "Anotacao", "Caches", "Local"],
                      [[f"`{c['fqn']}`", f"@{c['anotacao']}", ", ".join(c["caches"]) or "-", f"`{c['at']}`"]
                       for c in W["caches"][:40]]) + [""]
    if W["resilience"]:
        L += ["## Resiliencia e execucao assincrona", ""]
        L += md_table(["Alvo", "Anotacao", "Argumentos", "Local"],
                      [[f"`{r['fqn']}`", f"@{r['anotacao']}", f"`{r['args']}`" if r["args"] else "-", f"`{r['at']}`"]
                       for r in W["resilience"][:40]]) + [""]
    if D.get("android"):
        L += ["## Componentes Android declarados", ""]
        L += md_table(["Tipo", "Classe", "Manifesto"],
                      [[a["tipo"], f"`{a['classe']}`", f"`{a['arquivo']}`"] for a in D["android"][:40]]) + [""]
    if len(L) <= 6:
        L.append("Nenhum comportamento declarado por anotacao foi detectado.")
    w.write(f"{cfg['docs_dir']}/RUNTIME.md", "\n".join(L))


def persistence_sections(D: dict) -> list:
    """Secoes de entidades JPA, mappers MyBatis e changelogs Liquibase."""
    L: list = []
    if D.get("jpa"):
        L += ["", "## Entidades JPA", ""]
        for e in D["jpa"]:
            L.append(f"### `{e['tipo']}` → tabela `{e['tabela']}`")
            L.append(f"`{e['at']}`")
            if e["colunas"]:
                L += ["", "| Campo | Coluna | Tipo | Chave |", "|---|---|---|---|"]
                for c in e["colunas"][:40]:
                    L.append(f"| `{c['campo']}` | `{c['coluna']}` | `{c['tipo'] or '?'}` | {'sim' if c['id'] else ''} |")
            if e["relacoes"]:
                L += ["", "Relacoes:", ""]
                L += [f"- `{r['campo']}` {r['tipo']} → `{r['alvo'] or '?'}`" + (f" (coluna `{r['coluna']}`)" if r["coluna"] else "")
                      for r in e["relacoes"]]
            L.append("")
    xml = D.get("xml") or {}
    if xml.get("mybatis"):
        L += ["## Mappers MyBatis", ""]
        for m in xml["mybatis"]:
            L += [f"### `{m['namespace'] or m['arquivo']}`", f"`{m['arquivo']}`", ""]
            L += md_table(["Statement", "Tipo", "Tabelas"],
                          [[f"`{st['id']}`", st["tipo"], ", ".join(f"`{t}`" for t in st["tabelas"]) or "-"]
                           for st in m["statements"][:40]]) + [""]
    if xml.get("liquibase"):
        ops = Counter((c["op"], c["tabela"]) for c in xml["liquibase"])
        L += ["## Changelogs Liquibase", ""]
        L += md_table(["Operacao", "Tabela", "Ocorrencias"],
                      [[op, f"`{t}`", n] for (op, t), n in sorted(ops.items())][:60], "llr") + [""]
    return L


def emit_runtime_store(G: "Graph", D: dict, w: "Writer") -> None:
    sd = G.cfg["state_dir"]
    W = D["wiring"]
    write_jsonl(w, f"{sd}/wiring.jsonl", (
        [{"kind": "bean", **b} for b in W["beans"]] + [{"kind": "condition", **c} for c in W["conditions"]]
        + [{"kind": "transaction", **t} for t in W["transactions"]] + [{"kind": "cache", **c} for c in W["caches"]]
        + [{"kind": "resilience", **r} for r in W["resilience"]]
        + [{"kind": "android", **a} for a in D.get("android", [])]))
    if D.get("jpa"):
        write_jsonl(w, f"{sd}/jpa.jsonl", D["jpa"])
    emit_runtime(G, D, w)


def cmd_runtime(st: "Store", a) -> None:
    rows = _load_rows(st, "wiring.jsonl")
    if a.terms:
        t = a.terms[0].lower()
        rows = [r for r in rows if t in json.dumps(r, ensure_ascii=False).lower()]
    if a.json:
        out_json(rows[:a.limit])
        return
    if not rows:
        print("Nenhum comportamento declarado por anotacao foi indexado.")
        return
    cur = None
    for r in rows[:a.limit]:
        if r["kind"] != cur:
            cur = r["kind"]
            print(f"\n[{cur}]")
        if cur == "bean":
            print(f"  {r['tipo']} <- {', '.join(r['implementacao']) or '?'}   ({r['at']})")
        elif cur == "condition":
            print(f"  {r['fqn']}  @{r['anotacao']} {', '.join(r['valores'])}   ({r['at']})")
        elif cur == "transaction":
            print(f"  {r['fqn']}  ({r['escopo']}) {r['args']}   ({r['at']})")
        elif cur == "android":
            print(f"  {r['tipo']}: {r['classe']}")
        else:
            print(f"  {r['fqn']}  @{r.get('anotacao', '')} {r.get('args', '') or ', '.join(r.get('caches', []))}   ({r['at']})")


def cmd_entity(st: "Store", a) -> None:
    rows = _load_rows(st, "jpa.jsonl")
    if a.terms:
        t = a.terms[0].lower()
        rows = [r for r in rows if t in r["tipo"].lower() or t in r["tabela"].lower()]
    if a.json:
        out_json(rows[:a.limit])
        return
    if not rows:
        print("Nenhuma entidade JPA indexada.")
        return
    for e in rows[:a.limit]:
        print(f"\n{e['tipo']} → tabela {e['tabela']}   ({e['at']})")
        for c in e["colunas"][:30]:
            print(f"    {c['campo']:24} {c['coluna']:24} {c['tipo'] or '?'}" + ("  [id]" if c["id"] else ""))
        for r in e["relacoes"]:
            print(f"    {r['campo']:24} {r['tipo']} -> {r['alvo'] or '?'}")


def token_economy(st: "Store") -> dict:
    """Mede de verdade (rodando cmd_show, nao formula) quanto uma consulta pontual custa
    contra ler manualmente o(s) arquivo(s) equivalentes, mais o tamanho bruto do indice pra
    referencia. Os dois numeros NAO sao a mesma coisa: consulta pontual e mais barata que
    leitura manual (isso e a economia real); o indice bruto por inteiro e MAIOR que o
    codigo-fonte (json/docs nao sao pra leitura em massa, so consulta/grep pontual) — reportar
    os dois sem misturar evita um indicador que engana por omissao."""
    candidates = sorted((i for i in st.syms if st.syms[i].get("fan_in")),
                         key=lambda i: -st.syms[i]["fan_in"])[:10]
    amostra = []
    for i in candidates:
        s = st.syms[i]
        args = argparse.Namespace(terms=[str(i)], json=False, all=False, limit=25)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                cmd_show(st, args)
        except SystemExit:
            continue
        query_bytes = len(buf.getvalue().encode("utf-8"))
        files = {s["file"]} | {st.syms[e["s"]]["file"] for e in st.inc.get(i, [])}
        manual_bytes = 0
        for f in files:
            try:
                manual_bytes += (st.root / f).stat().st_size
            except OSError:
                pass
        if manual_bytes <= 0:
            continue
        amostra.append({"fqn": s["fqn"], "consulta_bytes": query_bytes, "manual_bytes": manual_bytes,
                         "arquivos_manuais": len(files)})
    media_pct = None
    if amostra:
        tot_q = sum(x["consulta_bytes"] for x in amostra)
        tot_m = sum(x["manual_bytes"] for x in amostra)
        media_pct = 1 - (tot_q / tot_m) if tot_m else None

    def _dir_bytes(rel_dir: str, pattern: str) -> int:
        base = st.root / rel_dir
        if not base.is_dir():
            return 0
        return sum(p.stat().st_size for p in base.rglob(pattern) if p.is_file())

    source_bytes = 0
    for f in st.files:
        try:
            source_bytes += (st.root / f).stat().st_size
        except OSError:
            pass
    footprint = {"codigo_fonte": source_bytes, "docs": _dir_bytes(st.cfg["docs_dir"], "*.md"),
                 "jsonl": _dir_bytes(st.cfg["state_dir"], "*.jsonl")}
    return {"amostra": amostra, "media_pct_economia": media_pct, "footprint": footprint}


def cmd_doctor(st: "Store", a) -> None:
    """Diagnostico do proprio indice: o que pode estar incompleto e por que."""
    store_extras(st)
    store_deep(st)
    m = st.manifest
    t = m["totals"]
    total_calls = t["calls_resolved"] + t["calls_unresolved"]
    rate = t["calls_resolved"] / total_calls if total_calls else 1.0
    issues = []
    if rate < 0.45:
        reasons = t.get("unresolved_reasons") or {}
        top = ", ".join(f"{k} ({v})" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:3])
        issues.append(("resolucao de chamadas baixa",
                       f"{rate:.0%} das chamadas resolvidas. Comum quando ha muito codigo gerado, "
                       "DSL ou dependencias externas. Grafo e impacto ficam subestimados."
                       + (f" Principais motivos: {top}." if top else "")))
    if t["parse_errors"]:
        issues.append(("arquivos com parse parcial",
                       f"{t['parse_errors']} arquivo(s). Veja a secao correspondente em ANALYSIS.md."))
    if not t["entrypoints"]:
        issues.append(("nenhum entrypoint",
                       "Sem entrada detectada, fatias e alcancabilidade ficam vazias. "
                       "Se o projeto usa anotacoes proprias, adicione-as em entry_annotations no .claude-indexer.json."))
    if not st.tables:
        issues.append(("nenhuma tabela", "Nao achei DDL, entidade nem SQL embutido. Se o SQL vem de constantes ou arquivos externos, o mapa de dados fica vazio."))
    if not st.coverage:
        issues.append(("sem cobertura estrutural", "Nenhum teste alcanca codigo de producao pelo grafo."))
    mods_sem_build = [k for k, v in st.modules.items() if not v.get("build")]
    if mods_sem_build:
        issues.append(("modulos sem arquivo de build",
                       ", ".join(mods_sem_build[:6]) + " — dependencias podem estar incompletas."))
    if not st.coupling:
        issues.append(("sem historico git", "Churn, acoplamento historico e parte do risco ficam sem dados."))
    if m.get("parser") != PARSER_VERSION:
        issues.append(("indice de outra versao do parser",
                       f"gerado com parser {m.get('parser')}, script atual e parser {PARSER_VERSION}. "
                       f"Rode `python {script_rel(st.root)} --full` para reparsear."))
    econ = token_economy(st)
    if a.json:
        out_json({"resolucao": round(rate, 3), "totais": t, "alertas": [{"item": i, "detalhe": d} for i, d in issues],
                  "token_economy": econ})
        return
    print(f"Indice de {m['project']['name']} — versao {m['version']}, parser {m['parser']}")
    print(f"  {t['source_files']} arquivos, {t['symbols']} simbolos, {t['edges']} arestas")
    print(f"  chamadas resolvidas: {rate:.0%} ({t['calls_resolved']} de {total_calls})")
    print(f"  entrypoints: {t['entrypoints']} · tabelas: {len(st.tables)} · fatias: {len(st.features)}")
    if econ["amostra"]:
        n = len(econ["amostra"])
        avg_q = sum(x["consulta_bytes"] for x in econ["amostra"]) / n
        avg_m = sum(x["manual_bytes"] for x in econ["amostra"]) / n
        pct = econ["media_pct_economia"]
        print(f"\n  Economia de tokens ({n} simbolos mais centrais, consulta real vs leitura manual):")
        print(f"    media: consulta {avg_q:.0f}B, leitura manual {avg_m:.0f}B"
              + (f" (~{pct:.0%} menor)" if pct is not None else ""))
    fp = econ["footprint"]
    print("\n  Footprint do indice (referencia, NAO e indicador de economia — nao e pra leitura em massa):")
    print(f"    codigo-fonte: {fp['codigo_fonte']:,}B · docs/: {fp['docs']:,}B · jsonl: {fp['jsonl']:,}B".replace(",", "."))
    if not issues:
        print("\n  Nenhum alerta. O indice parece completo para este projeto.")
        return
    print(f"\n  {len(issues)} ponto(s) de atencao:\n")
    for item, detail in issues:
        print(f"  - {item}: {detail}")


QUERIES = {
    "find": cmd_find, "show": cmd_show, "members": cmd_members, "file": cmd_file, "impact": cmd_impact,
    "path": cmd_path, "deps": cmd_deps, "endpoints": cmd_endpoints, "impl": cmd_impl, "uses": cmd_uses,
    "hotspots": cmd_hotspots, "dead": cmd_dead, "cycles": cmd_cycles, "tree": cmd_tree, "stats": cmd_stats,
    "runtime": cmd_runtime, "entity": cmd_entity, "doctor": cmd_doctor, "changed": cmd_changed, "risk": cmd_risk, "clones": cmd_clones, "unreachable": cmd_unreachable,
    "surface": cmd_surface, "coupled": cmd_coupled, "glossary": cmd_glossary, "accessors": cmd_accessors,
    "table": cmd_table, "config": cmd_config, "topic": cmd_topic, "tests": cmd_tests, "feature": cmd_feature,
    "similar": cmd_similar, "plan": cmd_plan, "churn": cmd_churn, "why": cmd_why, "conventions": cmd_conventions,
    "callers": lambda st, a: cmd_graph(st, a, "in", CALL_KINDS + ("overrides",), "Quem chama"),
    "callees": lambda st, a: cmd_graph(st, a, "out", FOLLOW_KINDS, "O que chama"),
    "branches": cmd_branches,
}
NEEDS_ARG = {"show", "members", "file", "impact", "callers", "callees", "impl", "uses", "tests", "similar", "plan", "why", "accessors", "branches"}


# =========================================================================== #
# Execucao: index, check, watch, workspace
# =========================================================================== #
def run_index(root: Path, args) -> int:
    cfg = load_config(root)
    for k in ("docs_dir", "state_dir"):
        v = getattr(args, k, None)
        if v:
            cfg[k] = v.strip("/")
    if getattr(args, "no_module_claude", False):
        cfg["module_claude_md"] = False
    if getattr(args, "no_settings", False):
        cfg["write_settings"] = False
    dry = bool(getattr(args, "dry_run", False) or getattr(args, "check", False))
    quiet = bool(getattr(args, "quiet", False))
    if not quiet:
        print(f"Indexando {root}...", file=sys.stderr)
    P = collect(root, cfg, full=bool(getattr(args, "full", False)), quiet=quiet)
    G = Graph(P).build()
    A = analyze(G)
    D = discover(G, A, quiet=quiet)
    deep_analysis(G, A, D, root, cfg, write=not dry, quiet=quiet)
    w = Writer(root, dry)
    man = emit_store(G, A, w, D)
    for label, fn in (("discovery", lambda: emit_discovery(G, A, D, w)),
                      ("analises profundas", lambda: emit_deep(G, A, D, w)),
                      ("runtime", lambda: emit_runtime_store(G, D, w)),
                      ("indice", lambda: emit_index(G, A, man, w)),
                      ("arvore", lambda: emit_tree(G, w)),
                      ("analise", lambda: emit_analysis(G, A, w)),
                      ("endpoints", lambda: emit_endpoints(G, w)),
                      ("fluxos", lambda: emit_flows(G, A, w)),
                      ("grafos", lambda: emit_graphs(G, A, w)),
                      ("api", lambda: emit_api(G, w)),
                      ("arquivos de agente", lambda: emit_agent_files(G, A, man, w, cfg, D))):
        safe(label, fn, None)
    w.prune(f"{cfg['docs_dir']}/api", ".md")
    if not dry and P["cache_out"] is not None:
        save_cache(root, cfg, P["cache_out"])
    t = man["totals"]
    if getattr(args, "check", False):
        if w.changed:
            print(f"[{root.name}] indice desatualizado ({len(w.changed)} arquivo(s)). Rode: python {script_rel(root)}", file=sys.stderr)
            for c in w.changed[:20]:
                print("  " + c, file=sys.stderr)
            return 1
        if not args.quiet:
            print(f"[{root.name}] indice atualizado.")
        return 0
    if not args.quiet:
        print(f"[{project_name(P)}] {t['source_files']} arquivos ({t['loc']} linhas), {t['modules']} modulos, "
              f"{t['types']} tipos, {t['functions']} funcoes, {t['edges']} arestas "
              f"— {P['parsed']} parseados, {P['cached']} em cache, {P['secs']:.1f}s")
        verb = "Mudariam" if dry else "Gerados/atualizados"
        print(f"{verb}: {len(w.changed)} arquivo(s)")
        if args.verbose:
            for c in w.changed:
                print("  " + c)
        d = D.get("diff", {})
        if not d.get("first_run", True):
            n = (len(d["added"]), len(d["changed"]) + len(d.get("resigned", [])), len(d["removed"]))
            if any(n):
                print(f"Desde a ultima execucao: {n[0]} novos, {n[1]} alterados, {n[2]} removidos "
                      f"— detalhe e impacto em {cfg['docs_dir']}/CHANGES.md")
                risky = [it for it in D.get("changed_impact", []) if not it["testes"]]
                if risky:
                    print(f"  {len(risky)} simbolo(s) alterados sem teste: " +
                          ", ".join(it["fqn"].rsplit(".", 1)[-1] for it in risky[:5]))
        else:
            print("Primeira indexacao: a proxima execucao ja mostra o que mudou e o impacto.")
        tot = t["calls_resolved"] + t["calls_unresolved"]
        rate = t["calls_resolved"] / tot if tot else 1.0
        if rate < 0.45 or t["parse_errors"] or not t["entrypoints"]:
            print(f"Qualidade do indice: {rate:.0%} das chamadas resolvidas"
                  + (f", {t['parse_errors']} arquivo(s) com parse parcial" if t["parse_errors"] else "")
                  + (", nenhum entrypoint detectado" if not t["entrypoints"] else "")
                  + f" — rode `python {script_rel(root)} query doctor`")
        h = man["health"]
        flags = [f"{h['module_cycles']} ciclos de modulo" if h["module_cycles"] else "",
                 f"{h['layer_violations']} violacoes de camada" if h["layer_violations"] else "",
                 f"{h['dead_candidates']} candidatos a codigo morto" if h["dead_candidates"] else "",
                 f"{t['parse_errors']} arquivos com parse parcial" if t["parse_errors"] else ""]
        flags = [f for f in flags if f]
        if flags:
            print("Atencao: " + "; ".join(flags) + f" — ver {cfg['docs_dir']}/ANALYSIS.md")
        print(f"Leia primeiro: CLAUDE.md, AGENTS.md, {cfg['docs_dir']}/INDEX.md")
    return 0


def fingerprint(root: Path, cfg: dict) -> tuple:
    out = []
    for path, size in list_files(root, cfg):
        ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
        if ext in SOURCE_EXTS or path.endswith(("pom.xml", ".gradle", ".gradle.kts", ".toml")):
            try:
                out.append((path, size, (root / path).stat().st_mtime_ns))
            except OSError:
                pass
    return tuple(out)


def run_watch(root: Path, args) -> int:
    cfg = load_config(root)
    interval = max(1.0, float(getattr(args, "interval", 2.0)))
    print(f"Observando {root} (Ctrl+C para sair)...")
    run_index(root, args)
    prev = fingerprint(root, cfg)
    try:
        while True:
            time.sleep(interval)
            cur = fingerprint(root, cfg)
            if cur != prev:
                prev = cur
                run_index(root, args)
    except KeyboardInterrupt:
        print("\nEncerrado.")
    return 0


def discover_projects(base: Path, depth: int = 3) -> list[Path]:
    found: list[Path] = []
    markers = ("settings.gradle.kts", "settings.gradle", "build.gradle.kts", "build.gradle", "pom.xml")
    def walk(d: Path, level: int) -> None:
        try:
            entries = sorted(d.iterdir())
        except OSError:
            return
        names = {e.name for e in entries}
        if names & set(markers):
            found.append(d)
            return
        if level >= depth:
            return
        for e in entries:
            if e.is_dir() and not e.is_symlink() and e.name not in DEFAULT_IGNORE_DIRS:
                walk(e, level + 1)
    walk(base, 0)
    return found


def run_workspace(base: Path, args) -> int:
    projects = discover_projects(base, args.depth)
    if not projects:
        print(f"Nenhum projeto Gradle/Maven encontrado em {base}.")
        return 1
    print(f"{len(projects)} projeto(s) encontrados.\n")
    rows = []
    rc = 0
    for p in projects:
        try:
            r = run_index(p, args)
            rc = rc or r
            man = json.loads((p / load_config(p)["state_dir"] / "manifest.json").read_text(encoding="utf-8"))
            t, h = man["totals"], man["health"]
            rows.append([man["project"]["name"], str(p.relative_to(base) if p != base else "."), t["modules"],
                         t["source_files"], t["loc"], t["types"], t["entrypoints"], h["module_cycles"], h["layer_violations"]])
        except SystemExit as e:  # noqa: PERF203
            err(f"{p}: {e}")
            rc = 1
        except Exception as e:  # noqa: BLE001
            err(f"{p}: {type(e).__name__}: {e}")
            rc = 1
    if rows and not args.quiet:
        lines = ["", "# Workspace", "", GEN_MARK, ""]
        lines += md_table(["Projeto", "Caminho", "Modulos", "Arquivos", "Linhas", "Tipos", "Entrypoints", "Ciclos", "Violacoes"], rows, "llrrrrrrr")
        txt = "\n".join(lines) + "\n"
        print(txt)
        if not args.dry_run:
            (base / "WORKSPACE-INDEX.md").write_text(txt.lstrip("\n"), encoding="utf-8")
            print(f"Resumo salvo em {base / 'WORKSPACE-INDEX.md'}")
    return rc


def run_query(root: Path, args) -> int:
    cfg = load_config(root)
    if args.cmd_name not in QUERIES:
        raise SystemExit(f"Consulta desconhecida: {args.cmd_name}. Opcoes: {', '.join(sorted(QUERIES))}")
    if args.cmd_name in NEEDS_ARG and not args.terms:
        raise SystemExit(f"'{args.cmd_name}' precisa de um argumento. Ex.: query {args.cmd_name} MinhaClasse")
    if args.cmd_name == "path" and len(args.terms) < 2:
        raise SystemExit("'path' precisa de dois argumentos: query path <origem> <destino>")
    st = Store(root, cfg)
    QUERIES[args.cmd_name](st, args)
    return 0


# =========================================================================== #
# CLI
# =========================================================================== #
EPILOG = """exemplos:
  python claude_indexer.py                          indexa a pasta atual
  python claude_indexer.py ../meu-projeto --full    reindexa do zero
  python claude_indexer.py index --check            falha se o indice estiver desatualizado (CI)
  python claude_indexer.py watch                    reindexa quando o codigo muda
  python claude_indexer.py workspace ~/projetos     indexa varios projetos
  python claude_indexer.py query find TransferService
  python claude_indexer.py query show br.app.core.TransferService
  python claude_indexer.py query impact TransferService --depth 4
  python claude_indexer.py query callers run --json
  python claude_indexer.py query plan "POST /api/v1/transfers"
  python claude_indexer.py query feature migracao
  python claude_indexer.py query table conta
  python claude_indexer.py query config spring.datasource
  python claude_indexer.py query similar TransferService
"""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="claude_indexer.py", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 description="Indexador global de projetos Kotlin/Java para agentes (Claude Code, Devin).",
                                 epilog=EPILOG)
    ap.add_argument("--version", action="version", version=f"claude_indexer {VERSION}")
    def common(p):
        p.add_argument("-q", "--quiet", action="store_true", help="sem saida (para hooks)")
        p.add_argument("-v", "--verbose", action="store_true", help="lista os arquivos alterados")
        p.add_argument("--dry-run", action="store_true", help="nao escreve nada")
        p.add_argument("--full", action="store_true", help="ignora o cache e reparseia tudo")
        p.add_argument("--docs-dir", help=f"pasta das docs (padrao: {DOCS_DIR})")
        p.add_argument("--state-dir", help=f"pasta do indice (padrao: {STATE_DIR})")
        p.add_argument("--no-module-claude", action="store_true", help="nao gera CLAUDE.md por modulo")
        p.add_argument("--no-settings", action="store_true", help="nao cria .claude/settings.json")
        p.add_argument("--log-file", help="tambem grava a saida (com timestamp) neste arquivo, em modo anexar")
        return p
    sub = ap.add_subparsers(dest="mode")
    idx = common(sub.add_parser("index", help="indexa o projeto (padrao)"))
    idx.add_argument("root", nargs="?", default=".")
    idx.add_argument("--check", action="store_true", help="CI: exit 1 se o indice estiver desatualizado")
    wt = common(sub.add_parser("watch", help="reindexa quando o codigo muda"))
    wt.add_argument("root", nargs="?", default=".")
    wt.add_argument("--interval", type=float, default=2.0)
    ws = common(sub.add_parser("workspace", help="descobre e indexa varios projetos"))
    ws.add_argument("root", nargs="?", default=".")
    ws.add_argument("--depth", type=int, default=3, help="profundidade da busca por projetos")
    q = sub.add_parser("query", help="consulta o indice ja gerado")
    q.add_argument("cmd_name", metavar="comando", help=", ".join(sorted(QUERIES)))
    q.add_argument("terms", nargs="*", metavar="arg")
    q.add_argument("--root", default=".", help="raiz do projeto indexado")
    q.add_argument("--json", action="store_true", help="saida JSON")
    q.add_argument("--limit", type=int, default=25)
    q.add_argument("--depth", type=int, default=3, help="profundidade do grafo (callers/callees/impact/impl)")
    q.add_argument("--kind", help="filtra por tipo de simbolo (find)")
    q.add_argument("--layer", help="filtra por camada (find)")
    q.add_argument("--regex", action="store_true", help="trata o termo como regex (find)")
    q.add_argument("--tests", action="store_true", help="inclui simbolos de teste (find)")
    q.add_argument("--all", action="store_true", help="mostra todos os membros (show)")
    return ap


def _default_to_index(argv: list[str]) -> list[str]:
    """'python claude_indexer.py [RAIZ] [flags]' funciona sem precisar digitar o subcomando
    'index' (uso documentado no EPILOG e no docstring do modulo): se o primeiro token nao for
    um modo valido nem uma opcao tratada pelo parser de topo (-h/--help/--version), insere
    'index' na frente antes de parsear. Sem isso, argparse tenta casar o primeiro token
    (ex.: um caminho) contra as opcoes do subcomando e falha com 'invalid choice'."""
    modes = {"index", "watch", "workspace", "query"}
    top_only = {"-h", "--help", "--version"}
    if not argv or (argv[0] not in modes and argv[0] not in top_only):
        return ["index"] + argv
    return argv


class _Tee:
    """Espelha cada escrita em stdout/stderr tambem para um arquivo (trilha de auditoria
    opcional, --log-file). Nao e um logger completo: so duplica o que ja seria impresso, sem
    mudar formato nem nivel algum."""

    def __init__(self, stream, fh):
        self.stream, self.fh = stream, fh

    def __getattr__(self, name):
        """Qualquer coisa alem de write/flush (isatty, encoding, ...) e do stream real —
        _Tee so precisa se meter na escrita, nao reimplementar um arquivo inteiro."""
        return getattr(self.stream, name)

    def write(self, data: str) -> int:
        n = self.stream.write(data)
        try:
            self.fh.write(data)
        except OSError:
            pass
        return n

    def flush(self) -> None:
        self.stream.flush()
        try:
            self.fh.flush()
        except OSError:
            pass


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    argv = _default_to_index(argv)
    ap = build_parser()
    args = ap.parse_args(argv)
    mode = args.mode or "index"
    log_path = getattr(args, "log_file", None)
    log_fh = None
    orig_out, orig_err = sys.stdout, sys.stderr
    if log_path and mode != "query":
        try:
            log_fh = open(log_path, "a", encoding="utf-8")
            log_fh.write(f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%S')} claude_indexer {mode} ===\n")
            sys.stdout, sys.stderr = _Tee(orig_out, log_fh), _Tee(orig_err, log_fh)
        except OSError as e:
            print(f"[aviso] nao foi possivel abrir --log-file {log_path}: {e}", file=sys.stderr)
            log_fh = None
    try:
        if mode == "query":
            return run_query(Path(args.root).resolve(), args)
        root = Path(getattr(args, "root", ".") or ".").resolve()
        if not root.is_dir():
            raise SystemExit(f"Nao e uma pasta: {root}")
        if mode == "watch":
            return run_watch(root, args)
        if mode == "workspace":
            return run_workspace(root, args)
        return run_index(root, args)
    finally:
        if log_fh:
            sys.stdout, sys.stderr = orig_out, orig_err
            log_fh.close()


if __name__ == "__main__":
    try:
        code = main()
    except KeyboardInterrupt:
        code = 130
    except BrokenPipeError:  # saida cortada por head/less
        code = 0
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    raise SystemExit(code)
