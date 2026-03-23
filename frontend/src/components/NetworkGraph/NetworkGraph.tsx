import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { useSimulationStore } from '../../store/simulationStore';
import type { NodeResult, EdgeResult, NodePosition, EdgeLink } from '../../types/network';

// ─── Color helpers ───────────────────────────────────────────────────────────

function pressureColor(p: number): string {
  if (p < 5) return '#ef4444';    // red — critical
  if (p < 10) return '#f97316';   // orange — low
  if (p < 25) return '#22c55e';   // green — good
  if (p < 50) return '#3b82f6';   // blue — normal
  return '#7c3aed';               // purple — high pressure
}

function velocityColor(v: number): string {
  if (v < 0.5)  return '#86efac';  // light green
  if (v < 1.5)  return '#fde68a';  // yellow
  if (v < 2.5)  return '#fb923c';  // orange
  return '#ef4444';                // red — bottleneck
}

function edgeStrokeWidth(flowLps: number): number {
  const abs = Math.abs(flowLps);
  if (abs < 1) return 1;
  return Math.min(1 + Math.log10(abs + 1) * 2.5, 7);
}

// ─── Node layout ─────────────────────────────────────────────────────────────

// Pre-compute approximate (x, y) positions based on the node naming scheme
// so the graph looks like a real city layout even without spring layout.
function getInitialPosition(nodeId: string): { x: number; y: number } {
  const cx = 500, cy = 400;

  if (nodeId === 'R1')     return { x: cx - 350, y: cy };
  if (nodeId === 'T1')     return { x: cx + 100, y: cy - 280 };
  if (nodeId === 'PS_IN')  return { x: cx - 200, y: cy + 20 };
  if (nodeId === 'PS_OUT') return { x: cx - 160, y: cy + 20 };

  // Ring main J01–J10 as a circle
  if (/^J0[1-9]$/.test(nodeId) || nodeId === 'J10') {
    const idx = parseInt(nodeId.slice(1)) - 1;
    const angle = (idx / 10) * 2 * Math.PI - Math.PI / 2;
    return { x: cx + 120 * Math.cos(angle), y: cy + 100 * Math.sin(angle) };
  }

  // North district J11–J30: upper area
  if (/^J[12][0-9]$/.test(nodeId)) {
    const idx = parseInt(nodeId.slice(1)) - 11;
    const col = idx % 5, row = Math.floor(idx / 5);
    return { x: cx - 160 + col * 90, y: cy - 160 - row * 70 };
  }

  // South district J31–J50: lower area
  if (/^J[34][0-9]$/.test(nodeId) || nodeId === 'J50') {
    const idx = parseInt(nodeId.slice(1)) - 31;
    const col = idx % 5, row = Math.floor(idx / 5);
    return { x: cx - 160 + col * 90, y: cy + 160 + row * 70 };
  }

  // Hill zone J51–J60: right side
  if (/^J[56][0-9]$/.test(nodeId)) {
    const idx = parseInt(nodeId.slice(1)) - 51;
    return { x: cx + 320 + (idx % 3) * 70, y: cy - 200 + Math.floor(idx / 3) * 80 };
  }

  return { x: cx + Math.random() * 200 - 100, y: cy + Math.random() * 200 - 100 };
}

// ─── Main component ───────────────────────────────────────────────────────────

const NetworkGraph: React.FC = () => {
  const svgRef = useRef<SVGSVGElement>(null);
  const result = useSimulationStore((s) => s.result);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; content: string } | null>(null);

  const buildGraph = useCallback(() => {
    if (!svgRef.current || !result) return;

    const width = svgRef.current.clientWidth || 1000;
    const height = svgRef.current.clientHeight || 600;

    // Index results
    const nodeMap = new Map<string, NodeResult>(result.nodes.map((n) => [n.node_id, n]));
    const edgeMap = new Map<string, EdgeResult>(result.edges.map((e) => [e.edge_id, e]));

    // Build position objects
    const nodePositions = new Map<string, NodePosition>();
    result.nodes.forEach((n) => {
      const pos = getInitialPosition(n.node_id);
      nodePositions.set(n.node_id, {
        id: n.node_id,
        x: pos.x,
        y: pos.y,
        node_type: n.node_type,
        elevation: n.elevation,
        pressure_m: n.pressure_m,
        demand: n.demand,
      });
    });

    const links: EdgeLink[] = result.edges.map((e) => ({
      id: e.edge_id,
      source: e.start_node,
      target: e.end_node,
      edge_type: e.edge_type,
      flow_lps: e.flow_lps,
      velocity: e.velocity,
      status: e.status,
    }));

    // Clear SVG
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    // Container with zoom
    const container = svg.append('g').attr('class', 'zoom-container');
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.2, 4])
        .on('zoom', (event) => container.attr('transform', event.transform))
    );

    // Draw edges
    const nodeArr = Array.from(nodePositions.values());
    const linkGroup = container.append('g').attr('class', 'links');

    links.forEach((link) => {
      const src = nodePositions.get(typeof link.source === 'string' ? link.source : (link.source as NodePosition).id);
      const tgt = nodePositions.get(typeof link.target === 'string' ? link.target : (link.target as NodePosition).id);
      if (!src || !tgt) return;

      const strokeColor =
        link.edge_type === 'pump' ? '#8b5cf6' :
        link.edge_type === 'valve' ? '#f59e0b' :
        velocityColor(link.velocity ?? 0);

      const sw = edgeStrokeWidth(link.flow_lps ?? 0);
      const er = edgeMap.get(link.id);

      linkGroup.append('line')
        .attr('x1', src.x).attr('y1', src.y)
        .attr('x2', tgt.x).attr('y2', tgt.y)
        .attr('stroke', strokeColor)
        .attr('stroke-width', sw)
        .attr('stroke-dasharray', link.status === 'closed' ? '4 3' : 'none')
        .attr('opacity', 0.85)
        .style('cursor', 'pointer')
        .on('mouseenter', (event) => {
          if (!er) return;
          setTooltip({
            x: event.offsetX + 12,
            y: event.offsetY + 12,
            content: [
              `${er.edge_id} (${er.edge_type})`,
              `Flow: ${er.flow_lps.toFixed(2)} L/s`,
              `Velocity: ${er.velocity.toFixed(2)} m/s`,
              `Head loss: ${er.head_loss.toFixed(2)} m`,
              `Status: ${er.status}`,
            ].join('\n'),
          });
        })
        .on('mouseleave', () => setTooltip(null));

      // Flow direction arrow (midpoint)
      if (Math.abs(link.flow_lps ?? 0) > 0.01) {
        const mx = (src.x + tgt.x) / 2;
        const my = (src.y + tgt.y) / 2;
        const dx = tgt.x - src.x;
        const dy = tgt.y - src.y;
        const len = Math.sqrt(dx * dx + dy * dy);
        const nx = dx / len, ny = dy / len;
        const dir = (link.flow_lps ?? 0) >= 0 ? 1 : -1;
        const px = nx * dir * 8, py = ny * dir * 8;

        linkGroup.append('polygon')
          .attr('points', `${mx + px},${my + py} ${mx - px - ny * 4},${my - py + nx * 4} ${mx - px + ny * 4},${my - py - nx * 4}`)
          .attr('fill', strokeColor)
          .attr('opacity', 0.7);
      }
    });

    // Draw nodes
    const nodeGroup = container.append('g').attr('class', 'nodes');
    nodeArr.forEach((node) => {
      const nr = nodeMap.get(node.id);
      const fill = node.node_type === 'reservoir' ? '#60a5fa' :
                   node.node_type === 'tank' ? '#a78bfa' :
                   pressureColor(node.pressure_m ?? 0);
      const r = node.node_type === 'junction' ? 8 : 12;

      const g = nodeGroup.append('g')
        .attr('transform', `translate(${node.x},${node.y})`)
        .style('cursor', 'pointer')
        .on('mouseenter', (event) => {
          if (!nr) return;
          setTooltip({
            x: event.offsetX + 12,
            y: event.offsetY + 12,
            content: [
              `${nr.node_id} (${nr.node_type})`,
              `Elevation: ${nr.elevation.toFixed(1)} m`,
              `Head: ${nr.hydraulic_head.toFixed(2)} m`,
              `Pressure: ${nr.pressure_m.toFixed(2)} m (${nr.pressure_kpa.toFixed(1)} kPa)`,
              `Demand: ${(nr.demand * 1000).toFixed(2)} L/s`,
            ].join('\n'),
          });
        })
        .on('mouseleave', () => setTooltip(null));

      if (node.node_type === 'tank') {
        g.append('rect')
          .attr('x', -r).attr('y', -r)
          .attr('width', r * 2).attr('height', r * 2)
          .attr('fill', fill).attr('stroke', '#fff').attr('stroke-width', 1.5);
      } else if (node.node_type === 'reservoir') {
        g.append('polygon')
          .attr('points', `0,${-r * 1.2} ${r * 1.1},${r * 0.8} ${-r * 1.1},${r * 0.8}`)
          .attr('fill', fill).attr('stroke', '#fff').attr('stroke-width', 1.5);
      } else {
        g.append('circle')
          .attr('r', r)
          .attr('fill', fill)
          .attr('stroke', '#1e293b')
          .attr('stroke-width', 1);
      }

      // Label for special nodes
      if (node.node_type !== 'junction') {
        g.append('text')
          .attr('dy', -r - 4)
          .attr('text-anchor', 'middle')
          .attr('font-size', '10px')
          .attr('fill', '#e2e8f0')
          .text(node.id);
      }
    });
  }, [result]);

  useEffect(() => {
    buildGraph();
  }, [buildGraph]);

  // Resize observer
  useEffect(() => {
    if (!svgRef.current) return;
    const observer = new ResizeObserver(() => buildGraph());
    observer.observe(svgRef.current);
    return () => observer.disconnect();
  }, [buildGraph]);

  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-400">
        <div className="text-5xl mb-4">🌊</div>
        <p className="text-lg font-medium">No simulation results yet</p>
        <p className="text-sm mt-1">Select a scenario and click Run Simulation</p>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full">
      <svg ref={svgRef} className="w-full h-full bg-slate-900 rounded-lg" />

      {/* Legend */}
      <div className="absolute top-2 right-2 bg-slate-800/90 rounded p-2 text-xs text-slate-300 space-y-1">
        <div className="font-semibold text-slate-200 mb-1">Pressure (nodes)</div>
        {[['< 5 m', '#ef4444'], ['5–10 m', '#f97316'], ['10–25 m', '#22c55e'], ['25–50 m', '#3b82f6'], ['> 50 m', '#7c3aed']].map(([label, color]) => (
          <div key={label} className="flex items-center gap-1">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
            <span>{label}</span>
          </div>
        ))}
        <div className="font-semibold text-slate-200 mt-2 mb-1">Velocity (pipes)</div>
        {[['< 0.5 m/s', '#86efac'], ['0.5–1.5', '#fde68a'], ['1.5–2.5', '#fb923c'], ['> 2.5', '#ef4444']].map(([label, color]) => (
          <div key={label} className="flex items-center gap-1">
            <div className="w-3 h-2 rounded" style={{ backgroundColor: color }} />
            <span>{label}</span>
          </div>
        ))}
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="absolute pointer-events-none bg-slate-800 border border-slate-600 rounded p-2 text-xs text-slate-200 whitespace-pre shadow-lg z-10"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.content}
        </div>
      )}
    </div>
  );
};

export default NetworkGraph;
