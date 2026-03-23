import React, { useCallback, useRef, useEffect, useState } from 'react';
import { GripHorizontal } from 'lucide-react';

interface Props {
  direction: 'vertical';
  onResize: (delta: number) => void;
}

const DragHandle: React.FC<Props> = ({ onResize }) => {
  const [dragging, setDragging] = useState(false);
  const lastY = useRef(0);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    lastY.current = e.clientY;
    setDragging(true);
  }, []);

  useEffect(() => {
    if (!dragging) return;

    const onMouseMove = (e: MouseEvent) => {
      const delta = lastY.current - e.clientY; // positive = dragging up = panel grows
      lastY.current = e.clientY;
      onResize(delta);
    };

    const onMouseUp = () => setDragging(false);

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [dragging, onResize]);

  return (
    <div
      onMouseDown={onMouseDown}
      className={`flex items-center justify-center h-2 cursor-ns-resize select-none border-b border-slate-700 transition-colors ${
        dragging ? 'bg-blue-600/30' : 'bg-slate-750 hover:bg-slate-600/40'
      }`}
    >
      <GripHorizontal size={14} className="text-slate-500" />
    </div>
  );
};

export default DragHandle;
