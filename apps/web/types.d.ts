// Add custom type declarations here (e.g. module '*.svg', env vars).

declare module '*.svg' {
  import { FC, SVGProps } from 'react';
  const content: FC<SVGProps<SVGElement>>;
  export default content;
}

declare module '*.svg?url' {
  const content: string;
  export default content;
}
