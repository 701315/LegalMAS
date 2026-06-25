// src/components/marketing/landing/EditorialHeroVisual.tsx

import React, { useEffect, useRef } from "react";

const EditorialHeroVisual: React.FC = () => {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    svgRef.current?.classList.add("hero-visual--ready");
  }, []);

  const ISO_SCALE = 38;
  const iso = (col: number, row: number): [number, number] => [
    210 + (col - row) * ISO_SCALE,
    135 + (col + row) * ISO_SCALE * 0.5,
  ];

  const edges: [number, number, number, number][] = [];
  for (let r = 0; r <= 3; r++) {
    for (let c = 0; c < 3; c++) {
      const [x1, y1] = iso(c, r);
      const [x2, y2] = iso(c + 1, r);
      edges.push([x1, y1, x2, y2]);
    }
  }
  for (let c = 0; c <= 3; c++) {
    for (let r = 0; r < 3; r++) {
      const [x1, y1] = iso(c, r);
      const [x2, y2] = iso(c, r + 1);
      edges.push([x1, y1, x2, y2]);
    }
  }

  type NodeDef = { x: number; y: number; accent: boolean; delay: number };
  const nodes: NodeDef[] = [];
  for (let r = 0; r <= 3; r++) {
    for (let c = 0; c <= 3; c++) {
      const [x, y] = iso(c, r);
      // Акцентные узлы — зелёные по брифу, спарсно
      const accent = r === 1 && c === 2;
      nodes.push({ x, y, accent, delay: (r * 4 + c) * 0.08 });
    }
  }

  const layerColors = [
    "rgba(255,255,255,0.80)",
    "rgba(255,255,255,0.60)",
    "rgba(255,255,255,0.42)",
    "rgba(255,255,255,0.24)",
  ];

  const layerHalf = 3 * ISO_SCALE + 6;
  const layerTilt = ISO_SCALE * 0.5 + 2;
  const baseY = 290;

  const makeLayer = (i: number) => {
    const cy = baseY - i * 18;
    const cx = 210;
    return [
      `${cx - layerHalf},${cy - layerTilt}`,
      `${cx},${cy - layerTilt * 2}`,
      `${cx + layerHalf},${cy - layerTilt}`,
      `${cx},${cy}`,
    ].join(" ");
  };

  const tailLines = [iso(3, 1), iso(3, 2), iso(3, 3), iso(2, 3)].map(
    ([x, y]) => ({ x, y })
  );

  return (
    <>
      <style>{`
        @keyframes heroFloat {
          0%,100% { transform: translateY(0px); }
          50%      { transform: translateY(-6px); }
        }
        @keyframes nodePop {
          0%   { opacity:0; transform:scale(0.4); }
          60%  { transform:scale(1.12); }
          100% { opacity:1; transform:scale(1); }
        }
        @keyframes edgeDraw {
          0%   { stroke-dashoffset: 80; opacity:0; }
          100% { stroke-dashoffset: 0;  opacity:1; }
        }
        @keyframes layerRise {
          0%   { opacity:0; transform:translateY(10px); }
          100% { opacity:1; transform:translateY(0); }
        }
        .hero-lattice-wrap {
          animation: heroFloat 8s ease-in-out infinite;
          transform-origin: center 140px;
        }
        .hero-visual--ready .hero-node {
          animation: nodePop 0.4s cubic-bezier(0.34,1.56,0.64,1) both;
        }
        .hero-visual--ready .hero-edge {
          stroke-dasharray: 80;
          animation: edgeDraw 0.6s ease both;
        }
        .hero-visual--ready .hero-layer {
          animation: layerRise 0.5s ease both;
        }
        @media (prefers-reduced-motion:reduce) {
          .hero-lattice-wrap, .hero-node, .hero-edge, .hero-layer {
            animation: none !important;
          }
        }
      `}</style>

      <div
        className="relative overflow-hidden rounded-[24px] border border-[#E5E2DA] bg-[#F1EFEA]"
        style={{ aspectRatio: "420/380" }}
      >
        {/* Тонкий radial highlight — без glow */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_35%_15%,rgba(255,255,255,0.5),transparent_50%)]" />

        <svg
          ref={svgRef}
          viewBox="0 0 420 380"
          width="100%"
          height="100%"
          aria-hidden="true"
          className="absolute inset-0"
        >
          {/* Слои — коммуницируют layered intelligence */}
          <g>
            {layerColors.map((fill, i) => (
              <polygon
                key={i}
                className="hero-layer"
                points={makeLayer(i)}
                fill={fill}
                stroke="rgba(17,24,39,0.07)"
                strokeWidth="0.75"
                style={{ animationDelay: `${i * 0.12}s` }}
              />
            ))}
          </g>

          <g className="hero-lattice-wrap">
            {/* Рёбра решётки */}
            {edges.map(([x1, y1, x2, y2], i) => (
              <line
                key={i}
                className="hero-edge"
                x1={x1} y1={y1} x2={x2} y2={y2}
                stroke="rgba(17,24,39,0.14)"
                strokeWidth="0.8"
                style={{ animationDelay: `${0.1 + i * 0.025}s` }}
              />
            ))}

            {/* Хвостовые линии — уходящие связи */}
            {tailLines.map((pt, i) => (
              <line
                key={`tail-${i}`}
                className="hero-edge"
                x1={pt.x} y1={pt.y}
                x2={pt.x + 22 + i * 6} y2={pt.y + 14 + i * 4}
                stroke="rgba(17,24,39,0.07)"
                strokeWidth="0.65"
                style={{ animationDelay: `${0.6 + i * 0.06}s` }}
              />
            ))}

            {/* Узлы — нейтральные + один акцентный зелёный */}
            {nodes.map(({ x, y, accent, delay }, i) => (
              <rect
                key={i}
                className="hero-node"
                x={x - 3} y={y - 3}
                width={6} height={6}
                rx={1}
                fill={accent ? "#2F5A4A" : "#111827"}
                opacity={accent ? 1 : 0.75}
                style={{
                  animationDelay: `${delay + 0.2}s`,
                  transformOrigin: `${x}px ${y}px`,
                }}
              />
            ))}
          </g>
        </svg>
      </div>
    </>
  );
};

export default EditorialHeroVisual;

