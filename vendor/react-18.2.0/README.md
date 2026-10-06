# React runtime for AVM

Unmodified production UMD distributions from npm packages `react@18.2.0` and
`react-dom@18.2.0`, the same versions previously requested from cdnjs by avm.html.
The MIT licenses are included. No account data or credentials are bundled.

The application no longer needs a CDN or Babel at runtime to render AVM.
`scripts/compile_avm.cjs` compiles its existing inline JSX using Babel 7.23.5.
These are third-party distributions, not locally authored application modules.
The existing architecture gate flags ReactDOM because it exceeds 100 KB; that
review requirement has not been suppressed or bypassed.
