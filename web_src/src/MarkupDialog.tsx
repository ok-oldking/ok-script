import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent } from "react";
import { Button, Input } from "@fluentui/react-components";
import {
  ArrowLeft20Regular,
  ArrowRight20Regular,
  Delete20Regular,
  Dismiss20Regular,
  Edit20Regular,
  Settings20Regular
} from "@fluentui/react-icons";
import { runtimeApi } from "./api";
import { ConfirmDeleteDialog } from "./ConfirmDialog";
import { t } from "./i18n";
import type { TemplateAnnotations, TemplateImage } from "./types";

type Annotation = TemplateAnnotations["annotations"][number];
type Mode = "none" | "draw" | "delete";
type Point = { x: number; y: number };
type BoxDraft = { index: number | null; category: string; bbox: number[] };
type DragState = {
  kind: "move" | "resize" | "pan";
  index: number;
  changed?: boolean;
  handle?: string;
  start: Point;
  originalBox?: number[];
  originalView?: number[];
};

const MIN_BOX_SIZE = 3;

function annotationColor(annotation: Annotation, index: number) {
  const id = Number(annotation.id ?? index + 1);
  const hue = Math.round(((id * 0.618033988749895) % 1) * 360);
  return `hsl(${hue} 78% 62%)`;
}

function clampBox(box: number[], width: number, height: number) {
  const w = Math.max(MIN_BOX_SIZE, Math.min(width, Math.round(box[2])));
  const h = Math.max(MIN_BOX_SIZE, Math.min(height, Math.round(box[3])));
  return [
    Math.max(0, Math.min(width - w, Math.round(box[0]))),
    Math.max(0, Math.min(height - h, Math.round(box[1]))),
    w,
    h
  ];
}

function BBoxEditor({ draft, images, imageName, onCancel, onConfirm }: {
  draft: BoxDraft;
  images: TemplateImage[];
  imageName: string;
  onCancel: () => void;
  onConfirm: (draft: BoxDraft) => void;
}) {
  const [value, setValue] = useState(draft);
  const owner = images.find((image) => image.name !== imageName && image.categories.includes(value.category.trim()));
  const error = !value.category.trim() ? t("Name required") : owner ? t("Already exists in '{name}'", { name: owner.name }) : "";
  const setCoordinate = (index: number, next: string) => setValue((current) => ({
    ...current,
    bbox: current.bbox.map((number, coordinate) => coordinate === index ? Math.max(0, Number(next) || 0) : number)
  }));
  return <div className="modal-backdrop bbox-editor-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
    <section className="modal bbox-editor" role="dialog" aria-modal="true" aria-label={t("Bounding Box")}>
      <header><strong>{t("Bounding Box")}</strong><button type="button" aria-label={t("Close")} onClick={onCancel}><Dismiss20Regular /></button></header>
      <form onSubmit={(event) => { event.preventDefault(); if (!error) onConfirm({ ...value, category: value.category.trim() }); }}>
        <label><span>{t("Category:")}</span><Input autoFocus value={value.category} placeholder={t("Category name")} onChange={(event) => setValue((current) => ({ ...current, category: event.target.value }))} />{error && <small>{error}</small>}</label>
        {["X", "Y", t("Width"), t("Height")].map((label, index) => <label key={String(label)}><span>{label}:</span><input type="number" min="0" max="99999" value={Math.round(value.bbox[index] ?? 0)} onChange={(event) => setCoordinate(index, event.target.value)} /></label>)}
        <footer><Button onClick={onCancel}>{t("Cancel")}</Button><Button appearance="primary" type="submit" disabled={Boolean(error)}>{t("OK")}</Button></footer>
      </form>
    </section>
  </div>;
}

export function MarkupDialog({ initial, images, notify, onClose }: {
  initial: TemplateAnnotations;
  images: TemplateImage[];
  notify: (message: string, intent: "success" | "info" | "error") => void;
  onClose: () => void;
}) {
  const [document, setDocument] = useState(initial);
  const [mode, setMode] = useState<Mode>("none");
  const [selected, setSelected] = useState(-1);
  const [hovered, setHovered] = useState(-1);
  const [drawStart, setDrawStart] = useState<Point | null>(null);
  const [drawPreview, setDrawPreview] = useState<Point | null>(null);
  const [draft, setDraft] = useState<BoxDraft | null>(null);
  const [deleteIndex, setDeleteIndex] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [imageSize, setImageSize] = useState({ width: initial.width || 1, height: initial.height || 1 });
  const [view, setView] = useState<number[]>([0, 0, initial.width || 1, initial.height || 1]);
  const [colorInfo, setColorInfo] = useState<{ text: string; rgb: string } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const pixelContext = useRef<CanvasRenderingContext2D | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const lastBoxPress = useRef<{ index: number; time: number } | null>(null);
  const currentIndex = Math.max(0, images.findIndex((image) => image.name === document.name));

  useEffect(() => {
    const image = new Image();
    image.onload = () => {
      const width = image.naturalWidth || document.width || 1;
      const height = image.naturalHeight || document.height || 1;
      setImageSize({ width, height });
      setView([0, 0, width, height]);
      const canvas = window.document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      context?.drawImage(image, 0, 0);
      pixelContext.current = context;
    };
    image.src = document.url;
    return () => { pixelContext.current = null; };
  }, [document.height, document.url, document.width]);

  const imageWidth = imageSize.width;
  const imageHeight = imageSize.height;

  const pointFromEvent = useCallback((event: { clientX: number; clientY: number }) => {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) return { x: 0, y: 0 };
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const transformed = point.matrixTransform(matrix.inverse());
    return { x: transformed.x, y: transformed.y };
  }, []);

  const persist = useCallback(async (annotations: Annotation[]) => {
    setDocument((current) => ({ ...current, annotations }));
    setSaving(true);
    try {
      const saved = await runtimeApi.saveTemplateAnnotations(document.name, annotations);
      setDocument(saved);
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : t("Action failed"), "error");
    } finally { setSaving(false); }
  }, [document.name, notify]);

  const loadImage = useCallback(async (index: number) => {
    const image = images[index];
    if (!image) return;
    try {
      const next = await runtimeApi.templateAnnotations(image.name);
      setDocument(next);
      setView([0, 0, next.width || 1, next.height || 1]);
      setSelected(-1);
      setHovered(-1);
      setMode("none");
      setDrawStart(null);
      setDrawPreview(null);
    } catch (reason) { notify(reason instanceof Error ? reason.message : t("Action failed"), "error"); }
  }, [images, notify]);

  const toggleMode = useCallback((next: Exclude<Mode, "none">) => {
    setMode((current) => current === next ? "none" : next);
    setDrawStart(null);
    setDrawPreview(null);
    dragRef.current = null;
  }, []);

  const openEditor = (index: number) => {
    const annotation = document.annotations[index];
    if (annotation) setDraft({ index, category: annotation.category, bbox: [...annotation.bbox] });
  };

  const deleteAnnotation = useCallback((index: number) => {
    const annotation = document.annotations[index];
    if (annotation) setDeleteIndex(index);
  }, [document.annotations]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (draft || deleteIndex !== null || event.ctrlKey || event.altKey || event.metaKey ||
          target?.matches("input, textarea, select, [contenteditable='true']")) return;

      const key = event.key.toLocaleLowerCase();
      if (key === "r") toggleMode("draw");
      else if (key === "d") toggleMode("delete");
      else if (event.key === "Delete" && selected >= 0) deleteAnnotation(selected);
      else if (event.key === "ArrowLeft") void loadImage(currentIndex - 1);
      else if (event.key === "ArrowRight") void loadImage(currentIndex + 1);
      else return;
      event.preventDefault();
    };

    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [currentIndex, deleteAnnotation, deleteIndex, draft, loadImage, selected, toggleMode]);

  const handleCanvasPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    const point = pointFromEvent(event);
    if (mode === "draw") {
      if (!drawStart) { setDrawStart(point); setDrawPreview(point); }
      else {
        const box = clampBox([Math.min(drawStart.x, point.x), Math.min(drawStart.y, point.y), Math.abs(point.x - drawStart.x), Math.abs(point.y - drawStart.y)], imageWidth, imageHeight);
        setDrawStart(null); setDrawPreview(null); setMode("none");
        if (box[2] >= MIN_BOX_SIZE && box[3] >= MIN_BOX_SIZE) setDraft({ index: null, category: "", bbox: box });
      }
      return;
    }
    setSelected(-1);
    if (view[2] < imageWidth || view[3] < imageHeight) {
      dragRef.current = { kind: "pan", index: -1, start: point, originalView: [...view] };
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  };

  const startBoxDrag = (event: ReactPointerEvent<SVGElement>, index: number, handle?: string) => {
    event.stopPropagation();
    if (mode === "delete") { deleteAnnotation(index); return; }
    if (mode !== "none") return;
    if (!handle) {
      const now = performance.now();
      const previous = lastBoxPress.current;
      lastBoxPress.current = { index, time: now };
      if (previous?.index === index && now - previous.time < 500) {
        lastBoxPress.current = null;
        dragRef.current = null;
        setSelected(index);
        openEditor(index);
        return;
      }
    }
    const point = pointFromEvent(event);
    setSelected(index);
    dragRef.current = { kind: handle ? "resize" : "move", index, handle, start: point, originalBox: [...document.annotations[index].bbox] };
    svgRef.current?.setPointerCapture(event.pointerId);
  };

  const updatePointer = (event: ReactPointerEvent<SVGSVGElement>) => {
    const point = pointFromEvent(event);
    const context = pixelContext.current;
    if (context && point.x >= 0 && point.y >= 0 && point.x < imageWidth && point.y < imageHeight) {
      const [r, g, b] = context.getImageData(Math.floor(point.x), Math.floor(point.y), 1, 1).data;
      setColorInfo({ rgb: `rgb(${r}, ${g}, ${b})`, text: `R:${r} G:${g} B:${b}  Abs: (${Math.floor(point.x)}, ${Math.floor(point.y)})  Rel: (${(point.x / imageWidth).toFixed(3)}, ${(point.y / imageHeight).toFixed(3)})` });
    }
    if (mode === "draw" && drawStart) setDrawPreview(point);
    const drag = dragRef.current;
    if (!drag) return;
    if (drag.kind === "pan" && drag.originalView) {
      const next = [...drag.originalView];
      next[0] = Math.max(0, Math.min(imageWidth - next[2], drag.originalView[0] - (point.x - drag.start.x)));
      next[1] = Math.max(0, Math.min(imageHeight - next[3], drag.originalView[1] - (point.y - drag.start.y)));
      setView(next);
      return;
    }
    if (!drag.originalBox) return;
    const [ox, oy, ow, oh] = drag.originalBox;
    const dx = point.x - drag.start.x;
    const dy = point.y - drag.start.y;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
    drag.changed = true;
    let next = drag.kind === "move" ? [ox + dx, oy + dy, ow, oh] : [ox, oy, ow, oh];
    if (drag.kind === "resize") {
      if (drag.handle?.includes("l")) { next[0] = ox + dx; next[2] = ow - dx; }
      if (drag.handle?.includes("r")) next[2] = ow + dx;
      if (drag.handle?.includes("t")) { next[1] = oy + dy; next[3] = oh - dy; }
      if (drag.handle?.includes("b")) next[3] = oh + dy;
    }
    next = clampBox(next, imageWidth, imageHeight);
    setDocument((current) => ({ ...current, annotations: current.annotations.map((annotation, index) => index === drag.index ? { ...annotation, bbox: next } : annotation) }));
  };

  const finishPointer = () => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (drag?.changed && drag.kind !== "pan") void persist(document.annotations);
  };

  const zoom = (event: ReactWheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    const point = pointFromEvent(event);
    const factor = event.deltaY < 0 ? 0.9 : 1.1;
    const width = Math.min(imageWidth, Math.max(imageWidth / 50, view[2] * factor));
    const height = Math.min(imageHeight, Math.max(imageHeight / 50, view[3] * factor));
    const x = Math.max(0, Math.min(imageWidth - width, point.x - (point.x - view[0]) * width / view[2]));
    const y = Math.max(0, Math.min(imageHeight - height, point.y - (point.y - view[1]) * height / view[3]));
    setView([x, y, width, height]);
  };

  const previewBox = useMemo(() => drawStart && drawPreview ? [Math.min(drawStart.x, drawPreview.x), Math.min(drawStart.y, drawPreview.y), Math.abs(drawPreview.x - drawStart.x), Math.abs(drawPreview.y - drawStart.y)] : null, [drawPreview, drawStart]);
  const selectedBox = selected >= 0 ? document.annotations[selected]?.bbox : null;
  const handleSize = Math.max(view[2], view[3]) / 120;
  const labelSize = Math.max(view[2], view[3]) / 85;
  const handles = selectedBox ? [["tl", selectedBox[0], selectedBox[1]], ["tr", selectedBox[0] + selectedBox[2], selectedBox[1]], ["bl", selectedBox[0], selectedBox[1] + selectedBox[3]], ["br", selectedBox[0] + selectedBox[2], selectedBox[1] + selectedBox[3]]] as const : [];

  return <div className="modal-backdrop markup-editor-backdrop">
    <section className="modal markup-editor-modal" role="dialog" aria-modal="true" aria-label={t("Markup Editor")}>
      <header><strong>{t("Markup Editor")}</strong><button type="button" aria-label={t("Close")} onClick={onClose}><Dismiss20Regular /></button></header>
      <div className="markup-editor-toolbar">
        <Button appearance={mode === "draw" ? "primary" : "secondary"} icon={<Edit20Regular />} onClick={() => toggleMode("draw")}>{t("Draw (R)")}</Button>
        <Button appearance={mode === "delete" ? "primary" : "secondary"} icon={<Delete20Regular />} onClick={() => toggleMode("delete")}>{t("Delete (D)")}</Button>
        <Button icon={<Settings20Regular />} disabled={selected < 0} onClick={() => openEditor(selected)}>{t("Modify (Double Click)")}</Button>
        <span className="markup-color-swatch" style={{ background: colorInfo?.rgb ?? "transparent" }} />
        <span className="markup-color-label">{colorInfo?.text}{colorInfo && ` (${t("Right click to copy color")})`}</span>
        <span className="markup-saving">{saving ? t("Saving...") : ""}</span>
        <span className="markup-image-name">{document.name} ({imageWidth}x{imageHeight})</span>
      </div>
      <div className="markup-editor-content">
        <Button className="markup-nav-button" appearance="subtle" icon={<ArrowLeft20Regular />} aria-label={t("Previous image")} disabled={currentIndex <= 0} onClick={() => void loadImage(currentIndex - 1)} />
        <div className={`markup-canvas ${mode !== "none" ? `mode-${mode}` : view[2] < imageWidth ? "is-zoomed" : ""}`}>
          <svg ref={svgRef} viewBox={view.join(" ")} preserveAspectRatio="xMidYMid meet" onPointerDown={handleCanvasPointerDown} onPointerMove={updatePointer} onPointerUp={finishPointer} onPointerCancel={finishPointer} onWheel={zoom} onContextMenu={(event) => { event.preventDefault(); if (colorInfo) void navigator.clipboard.writeText(colorInfo.rgb.replace("rgb", "").replaceAll(" ", "")); }}>
            <image href={document.url} x="0" y="0" width={imageWidth} height={imageHeight} preserveAspectRatio="none" />
            {document.annotations.map((annotation, index) => {
              const [x, y, width, height] = annotation.bbox;
              const active = selected === index;
              const color = active ? "#0078d4" : hovered === index ? "#ffa500" : annotationColor(annotation, index);
              return <g key={annotation.id ?? index} onPointerEnter={() => setHovered(index)} onPointerLeave={() => setHovered(-1)} onPointerDown={(event) => startBoxDrag(event, index)}>
                <rect className="markup-box-hit" x={x} y={y} width={width} height={height} />
                <rect className="markup-box" x={x} y={y} width={width} height={height} stroke={color} fill={color} />
                <text className="markup-box-label" x={x + labelSize * .18} y={Math.max(labelSize, y - labelSize * .18)} fill={color} fontSize={labelSize}>{annotation.category}</text>
              </g>;
            })}
            {previewBox && <rect className="markup-box-preview" x={previewBox[0]} y={previewBox[1]} width={previewBox[2]} height={previewBox[3]} />}
            {handles.map(([handle, x, y]) => <circle className={`markup-resize-handle handle-${handle}`} key={handle} cx={x} cy={y} r={handleSize} onPointerDown={(event) => startBoxDrag(event, selected, handle)} />)}
          </svg>
        </div>
        <Button className="markup-nav-button" appearance="subtle" icon={<ArrowRight20Regular />} aria-label={t("Next image")} disabled={currentIndex >= images.length - 1} onClick={() => void loadImage(currentIndex + 1)} />
      </div>
    </section>
    {draft && <BBoxEditor draft={draft} images={images} imageName={document.name} onCancel={() => setDraft(null)} onConfirm={(nextDraft) => {
      const annotation: Annotation = { category: nextDraft.category, bbox: clampBox(nextDraft.bbox, imageWidth, imageHeight) };
      const next = nextDraft.index === null ? [...document.annotations, annotation] : document.annotations.map((item, index) => index === nextDraft.index ? { ...item, ...annotation } : item);
      setDraft(null);
      setSelected(nextDraft.index ?? next.length - 1);
      void persist(next);
    }} />}
    {deleteIndex !== null && document.annotations[deleteIndex] && <ConfirmDeleteDialog name={document.annotations[deleteIndex].category} onCancel={() => setDeleteIndex(null)} onConfirm={() => {
      const next = document.annotations.filter((_item, index) => index !== deleteIndex);
      setDeleteIndex(null);
      setSelected(-1);
      void persist(next);
    }} />}
  </div>;
}
