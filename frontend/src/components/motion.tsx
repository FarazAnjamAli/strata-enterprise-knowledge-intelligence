"use client";

import { animate, motion, useInView, useMotionValue, useReducedMotion, type Variants } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";

const EASE = [0.2, 0.7, 0.2, 1] as const;

/** Fades + lifts its children in when they scroll into view. */
export function Reveal({
  children,
  delay = 0,
  y = 14,
  className,
  as = "div",
}: {
  children: React.ReactNode;
  delay?: number;
  y?: number;
  className?: string;
  as?: "div" | "section" | "li";
}) {
  const Comp = motion[as];
  return (
    <Comp
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -60px 0px" }}
      transition={{ duration: 0.55, delay, ease: EASE }}
    >
      {children}
    </Comp>
  );
}

const container: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.055, delayChildren: 0.05 } },
};
const item: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.42, ease: EASE } },
};

/** Staggered list: children wrapped in <StaggerItem> enter one after another. */
export function Stagger({ children, className, as = "div" }: { children: React.ReactNode; className?: string; as?: "div" | "ul" | "tbody" }) {
  const Comp = motion[as];
  return (
    <Comp className={className} variants={container} initial="hidden" whileInView="show" viewport={{ once: true, margin: "0px 0px -40px 0px" }}>
      {children}
    </Comp>
  );
}

export function StaggerItem({ children, className, as = "div" }: { children: React.ReactNode; className?: string; as?: "div" | "li" | "tr" }) {
  const Comp = motion[as];
  return (
    <Comp className={className} variants={item}>
      {children}
    </Comp>
  );
}

/** Counts up to `value` the first time it becomes visible. */
export function CountUp({ value, duration = 1.1, format = (n: number) => n.toLocaleString() }: { value: number; duration?: number; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const mv = useMotionValue(0);
  const [shown, setShown] = useState(reduce ? value : 0);
  useEffect(() => {
    if (!inView) return;
    if (reduce) return setShown(value);
    const ctl = animate(mv, value, { duration, ease: EASE, onUpdate: (v) => setShown(Math.round(v)) });
    return () => ctl.stop();
  }, [inView, value, duration, mv, reduce]);
  return <span ref={ref} className="tabular-nums">{format(shown)}</span>;
}

/** Branded loader: the three tiers light up in cascade. */
export function TierLoader({ className, label }: { className?: string; label?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-3", className)} role="status" aria-label={label ?? "Loading"}>
      <span className="flex flex-col gap-[3px]">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={cn("block h-[4px] w-[18px] -skew-x-[34deg] animate-cascade", i === 0 ? "bg-lime ring-1 ring-ink" : "bg-ink")}
            style={{ animationDelay: `${i * 0.18}s`, marginLeft: `${(2 - i) * 3}px` }}
          />
        ))}
      </span>
      {label && <span className="text-sm text-ink-2">{label}</span>}
    </span>
  );
}

/** Corner crop marks - a print-design detail used on hero surfaces. */
export function CropMarks({ className }: { className?: string }) {
  const c = "absolute h-3 w-3 border-ink";
  return (
    <span aria-hidden className={cn("pointer-events-none absolute inset-0", className)}>
      <span className={cn(c, "-left-px -top-px border-l border-t")} />
      <span className={cn(c, "-right-px -top-px border-r border-t")} />
      <span className={cn(c, "-bottom-px -left-px border-b border-l")} />
      <span className={cn(c, "-bottom-px -right-px border-b border-r")} />
    </span>
  );
}

/** Characters type in one by one (respects reduced motion). */
export function Typewriter({ text, delay = 0, speed = 28, className }: { text: string; delay?: number; speed?: number; className?: string }) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? text.length : 0);
  useEffect(() => {
    if (reduce) return;
    let i = 0;
    let t: ReturnType<typeof setTimeout>;
    const tick = () => {
      i += 1;
      setN(i);
      if (i < text.length) t = setTimeout(tick, speed);
    };
    t = setTimeout(tick, delay);
    return () => clearTimeout(t);
  }, [text, delay, speed, reduce]);
  return (
    <span className={className}>
      {text.slice(0, n)}
      {n < text.length && <span className="ml-0.5 inline-block h-[0.9em] w-[0.45em] translate-y-[0.1em] animate-blink bg-ink" />}
    </span>
  );
}
