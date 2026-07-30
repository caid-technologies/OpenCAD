import { useRef, useState } from "react";
import type { CadFileFormat } from "../types";

interface CadFileToolbarProps {
  canExport: boolean;
  onImport: (file: File) => Promise<void>;
  onExport: (format: CadFileFormat) => Promise<void>;
}

export function CadFileToolbar({ canExport, onImport, onExport }: CadFileToolbarProps): JSX.Element {
  const inputRef = useRef<HTMLInputElement>(null);
  const [format, setFormat] = useState<CadFileFormat>("step");
  const [busy, setBusy] = useState<"import" | "export" | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const runImport = async (file: File) => {
    setBusy("import");
    setMessage(null);
    try {
      await onImport(file);
      setMessage(`Imported ${file.name}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "CAD import failed.");
    } finally {
      setBusy(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const runExport = async () => {
    setBusy("export");
    setMessage(null);
    try {
      await onExport(format);
      setMessage(`Exported ${format.toUpperCase()}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "CAD export failed.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="cad-file-toolbar">
      <input
        ref={inputRef}
        className="cad-file-input"
        type="file"
        accept=".step,.stp,.stl"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void runImport(file);
        }}
      />
      <button
        className="cad-import-button"
        type="button"
        disabled={busy !== null}
        onClick={() => inputRef.current?.click()}
      >
        {busy === "import" ? "Importing…" : "Import CAD"}
      </button>
      <select
        aria-label="Export format"
        value={format}
        disabled={busy !== null}
        onChange={(event) => setFormat(event.target.value as CadFileFormat)}
      >
        <option value="step">STEP</option>
        <option value="stp">STP</option>
        <option value="stl">STL</option>
      </select>
      <button type="button" disabled={!canExport || busy !== null} onClick={() => void runExport()}>
        {busy === "export" ? "Exporting…" : "Export selected"}
      </button>
      {message ? <span className="cad-file-message" title={message}>{message}</span> : null}
    </div>
  );
}
