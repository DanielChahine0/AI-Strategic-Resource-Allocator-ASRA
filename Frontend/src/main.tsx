import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import ModelComparison from "./App";
import DatasetViewer from "./components/DatasetViewer";
import ErrorBoundary from "./components/ErrorBoundary";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/compare" element={<ModelComparison />} />
          <Route path="/dataset" element={<DatasetViewer />} />
          <Route path="*" element={<Navigate to="/compare" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
);
