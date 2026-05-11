/// <reference types="vite/client" />

import "react";

declare const __inputDirectoryAugmentationBrand: unique symbol;

declare module "react" {
  interface InputHTMLAttributes<T> {
    readonly [__inputDirectoryAugmentationBrand]?: T | undefined;
    webkitdirectory?: boolean | string;
    directory?: boolean | string;
  }
}


