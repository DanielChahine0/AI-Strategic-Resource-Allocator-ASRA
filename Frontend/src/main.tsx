import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import ModelComparison from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/compare" element={<ModelComparison />} />
        <Route path="*" element={<Navigate to="/compare" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
