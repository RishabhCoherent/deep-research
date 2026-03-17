"use client";

import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface FileDropZoneProps {
  accept: Record<string, string[]>;
  label: string;
  file: File | null;
  onFile: (file: File | null) => void;
}

export function FileDropZone({ accept, label, file, onFile }: FileDropZoneProps) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length > 0) onFile(accepted[0]);
    },
    [onFile]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    maxFiles: 1,
    multiple: false,
  });

  if (file) {
    return (
      <div className="glass-card flex items-center gap-4 p-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple/20">
          <FileText className="h-5 w-5 text-orange" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground truncate">
            {file.name}
          </p>
          <p className="text-xs text-warm-gray">
            {(file.size / 1024).toFixed(1)} KB
          </p>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onFile(null);
          }}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-warm-gray hover:bg-surface-3 hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-8 transition-all duration-300",
        isDragActive
          ? "border-orange bg-orange/5 glow-orange"
          : "border-surface-3 hover:border-warm-gray hover:bg-surface-2/30"
      )}
    >
      <input {...getInputProps()} />
      <div
        className={cn(
          "flex h-12 w-12 items-center justify-center rounded-xl transition-colors",
          isDragActive ? "bg-orange/20" : "bg-surface-3"
        )}
      >
        <Upload
          className={cn(
            "h-5 w-5 transition-colors",
            isDragActive ? "text-orange" : "text-warm-gray"
          )}
        />
      </div>
      <div className="text-center">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <p className="mt-1 text-xs text-warm-gray">
          Drag & drop or click to browse
        </p>
      </div>
    </div>
  );
}
