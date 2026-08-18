import { useMemo, useRef } from "react";
import type { KeyboardEvent, UIEvent } from "react";

const KEYWORDS = new Set([
  "and", "as", "assert", "async", "await", "break", "class", "continue", "def", "del", "elif",
  "else", "except", "False", "finally", "for", "from", "global", "if", "import", "in", "is",
  "lambda", "None", "nonlocal", "not", "or", "pass", "raise", "return", "True", "try", "while",
  "with", "yield"
]);

type Token = { text: string; kind?: "keyword" | "function" | "self" | "string" | "comment" | "number" };

function tokenize(line: string): Token[] {
  const tokens: Token[] = [];
  let index = 0;
  while (index < line.length) {
    const rest = line.slice(index);
    if (rest[0] === "#") { tokens.push({ text: rest, kind: "comment" }); break; }
    const string = rest.match(/^(?:[rRuUbBfF]{0,2})(?:'''[^']*'''|\"\"\"[^\"]*\"\"\"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")/);
    if (string) { tokens.push({ text: string[0], kind: "string" }); index += string[0].length; continue; }
    const number = rest.match(/^\b(?:0[xob][\da-f]+|\d+(?:\.\d+)?)\b/i);
    if (number) { tokens.push({ text: number[0], kind: "number" }); index += number[0].length; continue; }
    const word = rest.match(/^[A-Za-z_]\w*/);
    if (word) {
      const value = word[0];
      const following = line.slice(index + value.length);
      const kind = KEYWORDS.has(value) ? "keyword" : value === "self" ? "self" : /^\s*\(/.test(following) ? "function" : undefined;
      tokens.push({ text: value, kind }); index += value.length; continue;
    }
    const plain = rest.match(/^[^#'\"A-Za-z_\d]+/)?.[0] ?? rest[0];
    tokens.push({ text: plain }); index += plain.length;
  }
  return tokens;
}

function replaceSelection(textarea: HTMLTextAreaElement, value: string, onChange: (value: string) => void, unindent: boolean) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
  const selectionEnd = end > start && value[end - 1] === "\n" ? end - 1 : end;
  const lineEnd = value.indexOf("\n", selectionEnd);
  const blockEnd = lineEnd < 0 ? value.length : lineEnd;
  const block = value.slice(lineStart, blockEnd);
  const lines = block.split("\n");
  let deltaBeforeStart = 0;
  let totalDelta = 0;
  const changed = lines.map((line, lineIndex) => {
    const remove = unindent ? Math.min(4, line.match(/^ */)?.[0].length ?? 0) : 0;
    const prefix = unindent ? "" : "    ";
    const delta = prefix.length - remove;
    if (lineIndex === 0) deltaBeforeStart = delta;
    totalDelta += delta;
    return prefix + line.slice(remove);
  }).join("\n");
  onChange(value.slice(0, lineStart) + changed + value.slice(blockEnd));
  requestAnimationFrame(() => {
    textarea.selectionStart = Math.max(lineStart, start + deltaBeforeStart);
    textarea.selectionEnd = Math.max(textarea.selectionStart, end + totalDelta);
  });
}

export function PythonCodeEditor({ value, errorLine, onChange, onSave, editorRef }: {
  value: string;
  errorLine?: number;
  onChange: (value: string) => void;
  onSave: () => void;
  editorRef: React.RefObject<HTMLTextAreaElement | null>;
}) {
  const highlightRef = useRef<HTMLPreElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const lines = useMemo(() => value.split("\n"), [value]);
  const syncScroll = (event: UIEvent<HTMLTextAreaElement>) => {
    if (highlightRef.current) { highlightRef.current.scrollTop = event.currentTarget.scrollTop; highlightRef.current.scrollLeft = event.currentTarget.scrollLeft; }
    if (gutterRef.current) gutterRef.current.scrollTop = event.currentTarget.scrollTop;
  };
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.ctrlKey && event.key.toLocaleLowerCase() === "s") { event.preventDefault(); onSave(); return; }
    if (event.key === "Tab") {
      event.preventDefault();
      replaceSelection(event.currentTarget, value, onChange, event.shiftKey);
    }
  };
  return <div className="python-editor">
    <div ref={gutterRef} className="python-editor-gutter" aria-hidden="true">{lines.map((_line, index) => <span className={errorLine === index + 1 ? "error" : ""} key={index}>{index + 1}</span>)}</div>
    <div className="python-editor-code">
      <pre ref={highlightRef} className="python-editor-highlight" aria-hidden="true">{lines.map((line, index) => <span className={`python-line ${errorLine === index + 1 ? "error" : ""}`} key={index}>{tokenize(line).map((token, tokenIndex) => <span className={token.kind ? `python-${token.kind}` : undefined} key={tokenIndex}>{token.text}</span>)}{"\n"}</span>)}</pre>
      <textarea ref={editorRef} aria-label="Python code editor" spellCheck={false} value={value} onChange={(event) => onChange(event.target.value)} onScroll={syncScroll} onKeyDown={handleKeyDown} />
    </div>
  </div>;
}
