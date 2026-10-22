import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#FFFFFF",
        paper: "#FAFAF8",
        wash: "#F3F3F0",
        ink: {
          DEFAULT: "#0A0A0A",
          2: "#2E2E2E",
          3: "#555555",
        },
        line: {
          DEFAULT: "#E7E7E3",
          strong: "#CDCDC7",
        },
        lime: {
          DEFAULT: "#C6FF00",
          soft: "#F1FFC2",
          deep: "#9ACC00",
          ink: "#3D5200",
        },
        danger: { DEFAULT: "#D92D20", soft: "#FEF0EE" },
        amber: { DEFAULT: "#B54708", soft: "#FFF6E5" },
      },
      fontFamily: {
        sans: ["'Instrument Sans Variable'", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono Variable'", "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["10.5px", { lineHeight: "14px", letterSpacing: "0.06em" }],
      },
      borderRadius: { none: "0", xs: "2px", sm: "3px", DEFAULT: "4px", md: "6px" },
      boxShadow: {
        hair: "0 0 0 1px #E7E7E3",
        lift: "0 1px 0 #E7E7E3, 0 12px 32px -16px rgba(10,10,10,0.18)",
        pop: "0 0 0 1px #0A0A0A, 4px 4px 0 0 #C6FF00",
      },
      keyframes: {
        "fade-up": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        blink: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0" } },
        scan: { from: { transform: "translateX(-100%)" }, to: { transform: "translateX(100%)" } },
        pulseDot: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.35" } },
        cascade: {
          "0%, 100%": { opacity: "0.18", transform: "translateX(0)" },
          "30%": { opacity: "1", transform: "translateX(3px)" },
          "60%": { opacity: "0.18", transform: "translateX(0)" },
        },
        march: { to: { strokeDashoffset: "-24" } },
        shine: { from: { transform: "translateX(-120%) skewX(-20deg)" }, to: { transform: "translateX(260%) skewX(-20deg)" } },
        packet: {
          "0%": { top: "6%", opacity: "0" },
          "10%": { opacity: "1" },
          "70%": { opacity: "1" },
          "100%": { top: "94%", opacity: "0" },
        },
        marquee: { from: { transform: "translateX(0)" }, to: { transform: "translateX(-50%)" } },
        sweep: { "0%": { transform: "scaleX(0)", opacity: "1" }, "70%": { transform: "scaleX(1)", opacity: "1" }, "100%": { transform: "scaleX(1)", opacity: "0" } },
        float: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-6px)" } },
        gridDrift: { from: { backgroundPosition: "0 0" }, to: { backgroundPosition: "48px 48px" } },
      },
      animation: {
        "fade-up": "fade-up 360ms cubic-bezier(.2,.7,.2,1) both",
        blink: "blink 1s steps(1) infinite",
        scan: "scan 1.6s cubic-bezier(.4,0,.2,1) infinite",
        "pulse-dot": "pulseDot 1.4s ease-in-out infinite",
        cascade: "cascade 1.2s cubic-bezier(.4,0,.2,1) infinite",
        march: "march 0.8s linear infinite",
        shine: "shine 0.9s cubic-bezier(.4,0,.2,1)",
        packet: "packet 2.6s cubic-bezier(.6,0,.3,1) infinite",
        marquee: "marquee 38s linear infinite",
        sweep: "sweep 0.9s cubic-bezier(.2,.7,.2,1) forwards",
        float: "float 5s ease-in-out infinite",
        "grid-drift": "gridDrift 14s linear infinite",
      },
    },
  },
  plugins: [],
};
export default config;
