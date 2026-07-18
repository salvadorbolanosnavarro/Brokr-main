/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./*.html', './**/*.html', './app-shell.js', './sitio-engine.js'],
  theme: {
    screens: { sm: '640px', md: '768px', lg: '1024px', xl: '1280px', '2xl': '1440px' },
    extend: {
      colors: {
        navy: { 950: 'var(--sky-navy-deep)', 900: 'var(--sky-navy)', 800: 'var(--sky-navy-mid)' },
        blue: { 600: 'var(--sky-blue)', 700: 'var(--sky-blue-press)', 300: 'var(--sky-blue-lift)', 100: 'var(--sky-canvas)' },
        surface: { white: 'var(--surface-white)', off: 'var(--surface-off)', cold: 'var(--surface-cold)' },
        text: { primary: 'var(--text-primary)', secondary: 'var(--text-secondary)' },
        line: { DEFAULT: 'var(--line)', strong: 'var(--line-2)' },
      },
      fontFamily: { sans: ['var(--font-sans)'], display: ['var(--font-display)'], serif: ['var(--font-serif)'] },
      fontSize: {
        hero: ['var(--fs-hero)', { lineHeight: 'var(--lh-hero)', letterSpacing: '-0.045em' }],
        display: ['var(--fs-display)', { lineHeight: 'var(--lh-display)', letterSpacing: '-0.045em' }],
        h1: ['var(--fs-h1)', { lineHeight: 'var(--lh-h1)', letterSpacing: '-0.045em' }],
        h2: ['var(--fs-h2)', { lineHeight: 'var(--lh-h2)', letterSpacing: '-0.04em' }],
        body: ['var(--fs-body)', { lineHeight: '1.7' }],
        sm: ['var(--fs-sm)', { lineHeight: 'var(--lh-sm)' }],
        xs: ['var(--fs-xs)', { lineHeight: 'var(--lh-xs)' }],
      },
      spacing: Object.fromEntries(Array.from({ length: 25 }, (_, i) => [String(i), `var(--sp-${i})`]).filter(([k]) => !['0','9','11','13','14','15','17','18','19','21','22','23'].includes(k))),
      borderRadius: { sm: 'var(--r-sm)', DEFAULT: 'var(--r)', lg: 'var(--r-lg)', xl: 'var(--r-xl)', modal: 'var(--r-modal)', pill: 'var(--r-pill)' },
      boxShadow: { xs: 'var(--shadow-xs)', sm: 'var(--shadow-sm)', DEFAULT: 'var(--shadow)', md: 'var(--shadow-md)', lg: 'var(--shadow-lg)', xl: 'var(--shadow-xl)' },
      maxWidth: { page: 'var(--page-max)', form: 'var(--form-max)' },
    },
  },
  plugins: [],
};
