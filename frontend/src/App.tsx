import { Route, Routes } from "react-router-dom";
import { DryRunResults } from "./pages/DryRunResults";
import { EnumTranslationEditor } from "./pages/EnumTranslationEditor";
import { MappingEditor } from "./pages/MappingEditor";
import { ReconciliationResults } from "./pages/ReconciliationResults";
import { RetirementConfig } from "./pages/RetirementConfig";
import { RunHistory } from "./pages/RunHistory";
import { TablePicker } from "./pages/TablePicker";
import { ViewDefinitionEditor } from "./pages/ViewDefinitionEditor";
import { ViewPreviewResults } from "./pages/ViewPreviewResults";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<TablePicker />} />
      <Route path="/mappings/new" element={<MappingEditor />} />
      <Route path="/mappings/:mappingId" element={<MappingEditor />} />
      <Route path="/mappings/:mappingId/dry-run" element={<DryRunResults />} />
      <Route path="/enum-translations" element={<EnumTranslationEditor />} />
      <Route path="/retirement/new" element={<RetirementConfig />} />
      <Route path="/runs" element={<RunHistory />} />
      <Route path="/view-definitions/new" element={<ViewDefinitionEditor />} />
      <Route path="/view-definitions/:viewDefinitionId" element={<ViewDefinitionEditor />} />
      <Route path="/view-definitions/:viewDefinitionId/preview" element={<ViewPreviewResults />} />
      <Route
        path="/view-definitions/:viewDefinitionId/reconcile"
        element={<ReconciliationResults />}
      />
    </Routes>
  );
}
