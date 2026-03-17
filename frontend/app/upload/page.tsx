"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, FolderOpen, Upload, FileJson } from "lucide-react";
import { WizardLayout } from "@/components/WizardLayout";
import { FileDropZone } from "@/components/FileDropZone";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWizardStore } from "@/lib/store";
import { extractFiles, extractJson, extractFromPaths, extractJsonFromPath } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const setExtractionResult = useWizardStore((s) => s.setExtractionResult);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Tab 1: File paths
  const [pptxPath, setPptxPath] = useState("");
  const [xlsxPath, setXlsxPath] = useState("");

  // Tab 2: Upload files
  const [pptxFile, setPptxFile] = useState<File | null>(null);
  const [xlsxFile, setXlsxFile] = useState<File | null>(null);

  // Tab 3: JSON
  const [jsonFile, setJsonFile] = useState<File | null>(null);
  const [jsonPath, setJsonPath] = useState("");

  async function handleExtractPaths() {
    if (!pptxPath || !xlsxPath) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extractFromPaths(pptxPath, xlsxPath);
      setExtractionResult(res.extracted_data, res.summary);
      router.push("/extract");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Extraction failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleExtractFiles() {
    if (!pptxFile || !xlsxFile) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extractFiles(pptxFile, xlsxFile);
      setExtractionResult(res.extracted_data, res.summary);
      router.push("/extract");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Extraction failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadJson(file: File) {
    setLoading(true);
    setError(null);
    try {
      const res = await extractJson(file);
      setExtractionResult(res.extracted_data, res.summary);
      router.push("/extract");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid JSON file");
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadJsonPath() {
    if (!jsonPath) return;
    setLoading(true);
    setError(null);
    try {
      const res = await extractJsonFromPath(jsonPath);
      setExtractionResult(res.extracted_data, res.summary);
      router.push("/extract");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load JSON");
    } finally {
      setLoading(false);
    }
  }

  return (
    <WizardLayout currentStep={1}>
      <div className="mx-auto max-w-3xl animate-fade-in-up">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-foreground">Input Files</h2>
          <p className="mt-2 text-sm text-warm-gray">
            Upload or provide paths to your PowerPoint (TOC) and Excel (Market
            Estimate) files to begin.
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
            {error}
          </div>
        )}

        <div className="glass-card p-6">
          <Tabs defaultValue="paths" className="w-full">
            <TabsList className="grid w-full grid-cols-3 bg-surface-2">
              <TabsTrigger value="paths" className="gap-2">
                <FolderOpen className="h-3.5 w-3.5" />
                File Paths
              </TabsTrigger>
              <TabsTrigger value="upload" className="gap-2">
                <Upload className="h-3.5 w-3.5" />
                Upload Files
              </TabsTrigger>
              <TabsTrigger value="json" className="gap-2">
                <FileJson className="h-3.5 w-3.5" />
                Load JSON
              </TabsTrigger>
            </TabsList>

            {/* Tab 1: File Paths */}
            <TabsContent value="paths" className="mt-6 space-y-4">
              <p className="text-xs text-warm-gray">
                Enter the local file paths for the PowerPoint (TOC) and Excel
                (Market Estimate) files.
              </p>
              <div className="space-y-3">
                <div>
                  <Label className="text-xs text-muted-foreground">
                    Path to TOC file (.pptx)
                  </Label>
                  <Input
                    placeholder="C:\Users\...\TOC.pptx"
                    value={pptxPath}
                    onChange={(e) => setPptxPath(e.target.value)}
                    className="mt-1.5 bg-surface-2"
                  />
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">
                    Path to Market Estimate file (.xlsx)
                  </Label>
                  <Input
                    placeholder="C:\Users\...\ME_Data.xlsx"
                    value={xlsxPath}
                    onChange={(e) => setXlsxPath(e.target.value)}
                    className="mt-1.5 bg-surface-2"
                  />
                </div>
              </div>
              <Button
                onClick={handleExtractPaths}
                disabled={!pptxPath || !xlsxPath || loading}
                className="w-full gradient-brand text-white hover:opacity-90"
              >
                {loading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                Extract Data
              </Button>
            </TabsContent>

            {/* Tab 2: Upload Files */}
            <TabsContent value="upload" className="mt-6 space-y-4">
              <p className="text-xs text-warm-gray">
                Upload the PowerPoint (TOC) and Excel (Market Estimate) files.
              </p>
              <div className="grid grid-cols-2 gap-4">
                <FileDropZone
                  accept={{
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation":
                      [".pptx"],
                  }}
                  label="Table of Contents (.pptx)"
                  file={pptxFile}
                  onFile={setPptxFile}
                />
                <FileDropZone
                  accept={{
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                      [".xlsx"],
                  }}
                  label="Market Estimate (.xlsx)"
                  file={xlsxFile}
                  onFile={setXlsxFile}
                />
              </div>
              <Button
                onClick={handleExtractFiles}
                disabled={!pptxFile || !xlsxFile || loading}
                className="w-full gradient-brand text-white hover:opacity-90"
              >
                {loading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                Extract Data
              </Button>
            </TabsContent>

            {/* Tab 3: JSON */}
            <TabsContent value="json" className="mt-6 space-y-4">
              <p className="text-xs text-warm-gray">
                Upload a pre-extracted JSON file (from a previous extraction).
              </p>
              <FileDropZone
                accept={{ "application/json": [".json"] }}
                label="Pre-extracted JSON"
                file={jsonFile}
                onFile={(f) => {
                  setJsonFile(f);
                }}
              />
              {jsonFile && (
                <Button
                  onClick={() => handleLoadJson(jsonFile)}
                  disabled={loading}
                  className="w-full gradient-brand text-white hover:opacity-90"
                >
                  {loading ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  Load JSON
                </Button>
              )}

              <div className="relative my-4">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-surface-3" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-surface-1 px-3 text-warm-gray">
                    or enter path
                  </span>
                </div>
              </div>

              <div>
                <Label className="text-xs text-muted-foreground">
                  Path to JSON file
                </Label>
                <Input
                  placeholder="C:\Users\...\extracted_data.json"
                  value={jsonPath}
                  onChange={(e) => setJsonPath(e.target.value)}
                  className="mt-1.5 bg-surface-2"
                />
              </div>
              {jsonPath && (
                <Button
                  onClick={handleLoadJsonPath}
                  disabled={loading}
                  variant="outline"
                  className="w-full"
                >
                  {loading ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : null}
                  Load from Path
                </Button>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </WizardLayout>
  );
}
