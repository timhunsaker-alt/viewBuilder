import { Route, Routes } from "react-router-dom";
import { MappingEditor } from "./pages/MappingEditor";
import { TablePicker } from "./pages/TablePicker";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<TablePicker />} />
      <Route path="/mappings/new" element={<MappingEditor />} />
      <Route path="/mappings/:mappingId" element={<MappingEditor />} />
    </Routes>
  );
}
