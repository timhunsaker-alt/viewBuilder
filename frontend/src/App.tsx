import { Route, Routes } from "react-router-dom";
import { EnumTranslationEditor } from "./pages/EnumTranslationEditor";
import { MappingEditor } from "./pages/MappingEditor";
import { RetirementConfig } from "./pages/RetirementConfig";
import { TablePicker } from "./pages/TablePicker";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<TablePicker />} />
      <Route path="/mappings/new" element={<MappingEditor />} />
      <Route path="/mappings/:mappingId" element={<MappingEditor />} />
      <Route path="/enum-translations" element={<EnumTranslationEditor />} />
      <Route path="/retirement/new" element={<RetirementConfig />} />
    </Routes>
  );
}
