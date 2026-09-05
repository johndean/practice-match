/// <reference types="vite/client" />
interface ImportMetaEnv { readonly VITE_ENVIRONMENT?: 'qa' | 'production' | 'test' }
interface ImportMeta { readonly env: ImportMetaEnv }
