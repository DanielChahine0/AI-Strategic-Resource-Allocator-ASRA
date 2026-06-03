import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
// Type is the Apple system font (San Francisco) — provided by the OS, so no
// web fonts are loaded. Hierarchy comes from size, not weight.
import "./index.css";
import ErrorBoundary from "./components/ErrorBoundary";
import Impact from "./components/Impact";
import InventoryView from "./components/InventoryView";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/impact" element={<Impact />} />
          <Route path="/inventory" element={<InventoryView />} />
          <Route path="*" element={<Navigate to="/impact" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
);
