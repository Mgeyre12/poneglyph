import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: ["./pages/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: { "2xl": "1320px" },
    },
    extend: {
      fontFamily: {
        serif: ['"Cormorant Garamond"', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },

        sky: { DEFAULT: "hsl(var(--sky))", deep: "hsl(var(--sky-deep))" },
        ocean: "hsl(var(--ocean))",
        stone: { DEFAULT: "hsl(var(--stone))", deep: "hsl(var(--stone-deep))", light: "hsl(var(--stone-light))" },
        moss: { DEFAULT: "hsl(var(--moss))", bright: "hsl(var(--moss-bright))", dark: "hsl(var(--moss-dark))" },
        parchment: { DEFAULT: "hsl(var(--parchment))", deep: "hsl(var(--parchment-deep))" },
        brass: { DEFAULT: "hsl(var(--brass))", dim: "hsl(var(--brass-dim))" },
        crimson: { DEFAULT: "hsl(var(--crimson))", bright: "hsl(var(--crimson-bright))" },
        ink: "hsl(var(--ink))",

        sidebar: {
          DEFAULT: "hsl(var(--sidebar-background))",
          foreground: "hsl(var(--sidebar-foreground))",
          primary: "hsl(var(--sidebar-primary))",
          "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          border: "hsl(var(--sidebar-border))",
          ring: "hsl(var(--sidebar-ring))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 1px)",
        sm: "calc(var(--radius) - 2px)",
      },
      backgroundImage: {
        'gradient-sky': 'var(--gradient-sky)',
        'gradient-stone': 'var(--gradient-stone)',
        'gradient-crimson': 'var(--gradient-crimson)',
        'gradient-moss-fade': 'var(--gradient-moss-fade)',
      },
      boxShadow: {
        carved: 'var(--shadow-carved)',
        tablet: 'var(--shadow-tablet)',
        soft: 'var(--shadow-soft)',
      },
      keyframes: {
        "accordion-down": { from: { height: "0" }, to: { height: "var(--radix-accordion-content-height)" } },
        "accordion-up": { from: { height: "var(--radix-accordion-content-height)" }, to: { height: "0" } },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
