/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"SF Pro Display"',
          '"SF Pro Text"',
          '"Segoe UI"',
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif"
        ],
        mono: [
          '"SF Mono"',
          "Menlo",
          "Monaco",
          "Consolas",
          '"Liberation Mono"',
          '"Courier New"',
          "monospace"
        ]
      },
      colors: {
        apple: {
          gray: {
            50: "#FBFBFD",
            100: "#F5F5F7",
            200: "#E5E5EA",
            300: "#D1D1D6",
            400: "#C7C7CC",
            500: "#AEAEB2",
            600: "#8E8E93",
            700: "#636366",
            800: "#3A3A3C",
            900: "#1C1C1E",
            950: "#000000"
          },
          green: {
            DEFAULT: "#34C759",
            light: "#E8F8ED",
            dark: "#248A3D"
          },
          yellow: {
            DEFAULT: "#FFCC00",
            light: "#FFF9E6",
            dark: "#C69500"
          },
          red: {
            DEFAULT: "#FF3B30",
            light: "#FEECEB",
            dark: "#D70015"
          },
          blue: {
            DEFAULT: "#007AFF",
            light: "#EBF5FF",
            dark: "#0051A8"
          }
        }
      },
      boxShadow: {
        'apple-sm': '0 1px 2px rgba(0, 0, 0, 0.04), 0 1px 1px rgba(0, 0, 0, 0.02)',
        'apple-card': '0 4px 20px -2px rgba(0, 0, 0, 0.05), 0 2px 6px -1px rgba(0, 0, 0, 0.02)',
        'apple-hover': '0 8px 30px -4px rgba(0, 0, 0, 0.08), 0 4px 10px -2px rgba(0, 0, 0, 0.03)',
        'apple-glass': '0 8px 32px 0 rgba(0, 0, 0, 0.08)'
      }
    },
  },
  plugins: [],
}
