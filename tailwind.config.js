/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./lab/templates/**/*.html", "./**/forms.py"],
  theme: {
    extend: {
      colors: {
        primary: "#3b82f6", // Customize if needed
      }
    }
  },
  plugins: [],
}
