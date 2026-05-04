/// <reference types="vite/client" />

import "react";

declare module "react" {
  interface InputHTMLAttributes<T> {
    webkitdirectory?: boolean | string;
    directory?: boolean | string;
  }
}