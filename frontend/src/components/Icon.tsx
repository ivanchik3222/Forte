import { CSSProperties } from "react";

const paths = {
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9 M10 21h4",
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  history: "M3 11a9 9 0 1 1 2.5 7 M3 4v7h7 M12 7v5l3 2",
  book: "M12 6c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1v15",
  settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z",
  shield: "M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7z M8 12l3 3 5-6",
  upload: "M12 16V3 M7 8l5-5 5 5 M4 15v5h16v-5",
  arrow: "M4 12h16 M14 6l6 6-6 6",
  chevron: "m9 5 7 7-7 7",
  down: "m6 9 6 6 6-6",
  plus: "M12 5v14 M5 12h14",
  video: "M3 5h12v14H3z M15 10l6-4v12l-6-4",
  file: "M14 2H5v20h14V7z M14 2v6h5 M8 13h8 M8 17h6",
  check: "m5 12 4 4L19 6",
  checkCircle: "M22 11a10 10 0 1 1-6-8 M8 11l4 4L22 3",
  alert: "M12 3 2 21h20z M12 9v5 M12 17h.01",
  clock: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M12 6v6l4 2",
  lock: "M6 10h12v11H6z M8 10V6a4 4 0 0 1 8 0v4 M12 14v3",
  play: "m8 4 12 8-12 8z",
  scan: "M8 3H3v5 M16 3h5v5 M3 16v5h5 M21 16v5h-5 M7 12h10 M12 7v10",
  search: "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 M15 15l6 6",
  close: "m6 6 12 12 M6 18 18 6",
  download: "M12 3v13 M7 11l5 5 5-5 M4 17v4h16v-4",
  external: "M14 3h7v7 M21 3 10 14 M10 3H3v18h18v-7",
  info: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M12 11v6 M12 7h.01",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12 M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6",
  server: "M3 3h18v7H3z M3 14h18v7H3z M7 6.5h.01 M7 17.5h.01",
  help: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M9 8a3 3 0 0 1 6 0c0 2-3 2-3 5 M12 17h.01",
  user: "M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M4 21v-3a8 6 0 0 1 16 0v3",
  menu: "M4 6h16 M4 12h16 M4 18h16",
  refresh:
    "M21 3v6h-6 M3 21v-6h6 M5 8a8 8 0 0 1 13-3l3 4 M3 15l3 4a8 8 0 0 0 13-3",
  image: "M3 3h18v18H3z M3 17l6-6 4 4 3-3 5 5 M15 7h.01",
  logout: "M9 3H3v18h6 M8 12h13 M16 7l5 5-5 5",
} as const;

export type IconName = keyof typeof paths;
export function Icon({
  name,
  size = 20,
  className = "",
  style,
}: {
  name: IconName;
  size?: number;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
