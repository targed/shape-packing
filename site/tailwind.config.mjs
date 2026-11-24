import typography from '@tailwindcss/typography';

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: '#0b0f17',
        surface: {
          DEFAULT: '#111827',
          elevated: '#1a2234',
          hover: '#1e293b',
        },
        blueprint: {
          DEFAULT: '#0284c7',
          light: '#38bdf8',
          dark: '#0369a1',
        },
        cadmium: {
          DEFAULT: '#f59e0b',
          light: '#fbbf24',
          dark: '#d97706',
        },
        verify: {
          DEFAULT: '#10b981',
          light: '#34d399',
        },
        hairline: 'rgba(255, 255, 255, 0.08)',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      borderRadius: {
        sm: '4px',
        md: '6px',
        lg: '8px',
        xl: '12px',
      },
    },
  },
  plugins: [typography],
};
