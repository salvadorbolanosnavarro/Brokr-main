# Broquer en 5 países

México, Colombia, Perú, Argentina y Chile.

## Cómo funciona

- Cada cuenta pertenece a **un país** (`usuarios.pais`). Se elige en el landing
  o en la pantalla de crear cuenta y ya no se vuelve a preguntar. Desde el
  navegador no se puede cambiar después; solo Broquer (Supabase o backend).
- Quien se une al equipo de una empresa **hereda el país del dueño**.
- Las cuentas que ya existían quedaron en México.
- La configuración de cada país vive en dos archivos espejo:
  `paises.js` (pantallas) y `core/paises.py` (servidor).
  `tests/test_paises.py` revisa que digan lo mismo.

## Qué cambia por país

| | México | Colombia | Perú | Argentina | Chile |
|---|---|---|---|---|---|
| Moneda de inmuebles | MXN, USD | COP, USD | PEN, USD | USD, ARS | CLP, UF, USD |
| Valor del AVM en | MXN | COP | USD | USD | UF |
| Impuestos por venta | ISR (`isr.html`) | Ganancia ocasional | Renta 2.ª categoría | Cedular 15% | Mayor valor (8.000 UF) |
| Contratos de Broquer | Ley mexicana | Ley 820 / Código Civil | Código Civil (arras, allanamiento) | CCyC (locación, boleto) | Ley 18.101 / Código Civil |
| Cumplimiento (PLD) | Avisos XML al SAT | Reporte en SIREL (UIAF) | UIF-Perú | SRO (UIF) | UAF |
| Broquer Max y Empresas se cobran en | MXN | USD | USD | USD | USD |

La calculadora de los cuatro países nuevos es `impuestos.html`, con sus reglas
en `impuestos-reglas.js`. Los valores anuales (UVT, UIT, UF) se editan en la
pantalla; los valores por defecto están en `PARAMETROS` y hay que actualizarlos
cada año.

Fuera de México, Cumplimiento no genera avisos en XML: lleva el expediente
del cliente (sin CURP), las operaciones con un **monto de alerta interna**
que cada agencia ajusta, las operaciones inusuales y la bitácora. Los
contratos los arma `contratos_paises.py`; las etiquetas del formulario las
cambia `contratos-paises.js`.

## Pasos para activarlo

1. **Base de datos:** correr `migracion-paises.sql` y después
   `migracion-paises-2-buzon.sql` en Supabase → SQL Editor.
2. **Stripe:** en el producto Broquer Max agregar un precio mensual en **USD**
   y poner su ID (`price_…`) en la variable `STRIPE_PRICE_PRO_USD` del
   servidor. Sin ella, las cuentas fuera de México ven "El cobro en dólares
   todavía no está disponible" en vez de pagar en pesos. Para Broquer para
   Empresas, lo mismo con `STRIPE_PRICE_EMPRESA_MENSUAL_USD`,
   `STRIPE_PRICE_EMPRESA_ANUAL_USD`, `STRIPE_PRICE_EMPRESA_EXTRA_MENSUAL_USD` y
   `STRIPE_PRICE_EMPRESA_EXTRA_ANUAL_USD` (sugerido: US$189 al mes por 5
   lugares y US$33 por lugar extra; el anual, 11 meses).
3. **Legal:** los anexos por país (`legal-paises.js`), los contratos
   (`contratos_paises.py`) y los textos de Cumplimiento son una base; deben
   revisarlos abogados de cada país antes de vender allá.
4. **Impuestos de Broquer:** Colombia, Perú, Argentina y Chile cobran IVA/IGV a
   los servicios digitales del extranjero. Revisarlo con un contador.
5. **App de iPhone:** en App Store Connect, habilitar la app en esos países.

## Cambiar el país de una cuenta

Consola de dueño → Usuarios → elige la cuenta → fila **País**. Si la cuenta
es dueña de una empresa, su equipo cambia con ella.
