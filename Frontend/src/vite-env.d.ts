/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AI_API?: string;
  readonly VITE_RAG_API?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
