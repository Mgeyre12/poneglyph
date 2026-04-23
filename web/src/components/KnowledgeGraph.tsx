import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

type Node = { id: string; label: string; group: "character" | "fruit" | "location" | "org"; val?: number };
type Link = { source: string; target: string };

const NODES: Node[] = [
  { id: "luffy", label: "Monkey D. Luffy", group: "character", val: 5 },
  { id: "robin", label: "Nico Robin", group: "character", val: 4 },
  { id: "zoro", label: "Roronoa Zoro", group: "character", val: 4 },
  { id: "shanks", label: "Shanks", group: "character", val: 4 },
  { id: "blackbeard", label: "Blackbeard", group: "character", val: 4 },
  { id: "kaido", label: "Kaido", group: "character", val: 3 },
  { id: "bigmom", label: "Big Mom", group: "character", val: 3 },
  { id: "buggy", label: "Buggy", group: "character", val: 3 },
  { id: "ace", label: "Portgas D. Ace", group: "character", val: 3 },
  { id: "sabo", label: "Sabo", group: "character", val: 3 },
  { id: "garp", label: "Monkey D. Garp", group: "character", val: 3 },
  { id: "dragon", label: "Monkey D. Dragon", group: "character", val: 3 },
  { id: "akainu", label: "Akainu", group: "character", val: 3 },
  { id: "kuzan", label: "Kuzan", group: "character", val: 3 },
  { id: "doflamingo", label: "Doflamingo", group: "character", val: 3 },
  { id: "crocodile", label: "Crocodile", group: "character", val: 3 },

  { id: "gomu", label: "Gomu Gomu", group: "fruit", val: 3 },
  { id: "hana", label: "Hana Hana", group: "fruit", val: 3 },
  { id: "yami", label: "Yami Yami", group: "fruit", val: 3 },
  { id: "gura", label: "Gura Gura", group: "fruit", val: 3 },
  { id: "mera", label: "Mera Mera", group: "fruit", val: 3 },
  { id: "uo", label: "Uo Uo Seiryu", group: "fruit", val: 3 },
  { id: "soru", label: "Soru Soru", group: "fruit", val: 3 },
  { id: "ito", label: "Ito Ito", group: "fruit", val: 3 },
  { id: "suna", label: "Suna Suna", group: "fruit", val: 3 },

  { id: "wano", label: "Wano", group: "location", val: 3 },
  { id: "raftel", label: "Laugh Tale", group: "location", val: 4 },
  { id: "alabasta", label: "Alabasta", group: "location", val: 3 },
  { id: "marineford", label: "Marineford", group: "location", val: 3 },
  { id: "ohara", label: "Ohara", group: "location", val: 3 },
  { id: "dressrosa", label: "Dressrosa", group: "location", val: 3 },
  { id: "eastblue", label: "East Blue", group: "location", val: 2 },
  { id: "northblue", label: "North Blue", group: "location", val: 2 },

  { id: "straw", label: "Straw Hats", group: "org", val: 4 },
  { id: "marines", label: "Marines", group: "org", val: 4 },
  { id: "warlords", label: "Seven Warlords", group: "org", val: 3 },
  { id: "revolutionaries", label: "Revolutionary Army", group: "org", val: 3 },
  { id: "wb", label: "Whitebeard Pirates", group: "org", val: 3 },
  { id: "bb", label: "Blackbeard Pirates", group: "org", val: 3 },
  { id: "redhair", label: "Red Hair Pirates", group: "org", val: 3 },
  { id: "cp9", label: "CP9", group: "org", val: 2 },
];

const LINKS: Link[] = [
  ["luffy", "gomu"], ["luffy", "straw"], ["luffy", "garp"], ["luffy", "dragon"], ["luffy", "ace"], ["luffy", "sabo"], ["luffy", "shanks"], ["luffy", "eastblue"],
  ["robin", "hana"], ["robin", "straw"], ["robin", "ohara"],
  ["zoro", "straw"],
  ["ace", "mera"], ["ace", "wb"],
  ["sabo", "mera"], ["sabo", "revolutionaries"], ["sabo", "dragon"],
  ["blackbeard", "yami"], ["blackbeard", "gura"], ["blackbeard", "bb"],
  ["kaido", "uo"], ["kaido", "wano"],
  ["bigmom", "soru"],
  ["doflamingo", "ito"], ["doflamingo", "warlords"], ["doflamingo", "dressrosa"],
  ["crocodile", "suna"], ["crocodile", "warlords"], ["crocodile", "alabasta"],
  ["buggy", "warlords"],
  ["shanks", "redhair"], ["shanks", "marineford"],
  ["garp", "marines"], ["akainu", "marines"], ["kuzan", "marines"],
  ["dragon", "revolutionaries"],
  ["wb", "gura"], ["wb", "marineford"],
  ["straw", "wano"], ["straw", "alabasta"], ["straw", "dressrosa"],
  ["raftel", "luffy"],
  ["northblue", "doflamingo"], ["northblue", "kuzan"],
  ["cp9", "marines"],
].map(([s, t]) => ({ source: s, target: t }));

const colorFor = (g: Node["group"]) => {
  switch (g) {
    case "character": return "rgba(204, 144, 56, 0.95)";   // brass
    case "fruit":     return "rgba(180, 56, 70, 0.95)";    // crimson bright
    case "location":  return "rgba(92, 156, 100, 0.95)";   // moss bright
    case "org":       return "rgba(196, 170, 120, 0.95)";  // parchment deep
  }
};

type Props = {
  height?: number;
  interactive?: boolean;
  showLabels?: boolean;
};

export const KnowledgeGraph = ({ height = 480, interactive = true, showLabels = true }: Props) => {
  const wrapRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [w, setW] = useState(800);
  const data = useMemo(() => ({ nodes: NODES.map((n) => ({ ...n })), links: LINKS.map((l) => ({ ...l })) }), []);

  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      try {
        fgRef.current?.d3Force("charge")?.strength(-120);
        fgRef.current?.d3Force("link")?.distance(70);
        fgRef.current?.zoomToFit(600, 60);
      } catch {}
    }, 300);
    return () => clearTimeout(t);
  }, [w]);

  return (
    <div ref={wrapRef} className="relative w-full overflow-hidden rounded-sm" style={{ height }}>
      <ForceGraph2D
        ref={fgRef}
        graphData={data}
        width={w}
        height={height}
        backgroundColor="rgba(0,0,0,0)"
        cooldownTicks={120}
        enableZoomInteraction={interactive}
        enablePanInteraction={interactive}
        enableNodeDrag={interactive}
        linkColor={() => "rgba(180, 195, 205, 0.35)"}
        linkWidth={0.8}
        linkDirectionalParticles={interactive ? 1 : 0}
        linkDirectionalParticleSpeed={0.003}
        linkDirectionalParticleWidth={1.5}
        linkDirectionalParticleColor={() => "rgba(204, 144, 56, 0.7)"}
        nodeRelSize={4}
        nodeVal={(n: any) => n.val ?? 2}
        nodeCanvasObjectMode={() => "after"}
        nodeCanvasObject={(node: any, ctx, globalScale) => {
          const r = Math.sqrt(node.val ?? 2) * 3;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
          ctx.fillStyle = colorFor(node.group);
          ctx.fill();
          ctx.strokeStyle = "rgba(40, 56, 76, 0.9)";
          ctx.lineWidth = 1;
          ctx.stroke();

          if (showLabels && globalScale > 0.8 && (node.val ?? 0) >= 3) {
            const label = node.label;
            const fontSize = 10 / Math.max(globalScale, 1);
            ctx.font = `${fontSize}px "Cormorant Garamond", serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillStyle = "rgba(232, 232, 220, 0.92)";
            ctx.fillText(label, node.x, node.y + r + 2);
          }
        }}
      />
    </div>
  );
};
