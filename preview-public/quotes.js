/* ════════════════════════════════════════════════════════════════════
   BROQUER — Banco de frases compartido
   Fuente única para la frase rotativa del banner de Inicio (index.html)
   y la de la franja superior del resto de los módulos (app-shell.js).

   Antes cada uno tenía su propio arreglo QUOTES, sin sincronía entre
   ellos — así fue como una frase que contradice lo que el propio
   WhatsApp de Broquer promete ("Nadie recuerda cuánto tardaste en
   contestar. Todos recuerdan si contestaste.") vivió sola en el de
   Inicio sin que nadie la viera reflejada (o filtrada) en el resto de
   la app. Con un solo arreglo, revisar/editar las frases es revisar
   un solo lugar.

   Se expone como variable global (window.BROQUER_QUOTES) — el resto
   del sitio no usa bundler ni módulos ES, así que esto sigue el mismo
   patrón que MODS/ICONS en app-shell.js. Rota cada hora, de forma
   determinista, en cada página que lo consume.
   ════════════════════════════════════════════════════════════════════ */
window.BROQUER_QUOTES = [
  // — Mundo inmobiliario —
  { t: "Compra tierra: ya no la están haciendo.", a: "Mark Twain" },
  { t: "Los bienes raíces no se pueden perder ni robar, ni se los pueden llevar. Comprados con sentido común y pagados en su totalidad, son la inversión más segura del mundo.", a: "Franklin D. Roosevelt" },
  { t: "Ubicación, ubicación, ubicación.", a: "Máxima inmobiliaria" },
  { t: "El 90% de los millonarios se hicieron ricos invirtiendo en bienes raíces.", a: "Andrew Carnegie" },
  { t: "No esperes para comprar bienes raíces. Compra bienes raíces y espera.", a: "T. Harv Eker" },
  { t: "Nunca falta la tierra: falta la gente que la sepa vender.", a: "Refrán del gremio" },
  { t: "La mejor inversión sobre la faz de la Tierra es la Tierra misma.", a: "Louis Glickman" },
  { t: "En bienes raíces, la ganancia se hace al comprar, no al vender.", a: "Sabiduría inmobiliaria" },
  { t: "Las grandes fortunas de este país se han hecho en la tierra.", a: "John D. Rockefeller" },
  { t: "El terrateniente se enriquece incluso mientras duerme.", a: "John Stuart Mill" },
  { t: "No vendes una casa: ayudas a alguien a empezar su próximo capítulo.", a: "Voz del oficio" },
  { t: "Un cliente no compra metros cuadrados. Compra la vida que va a vivir ahí.", a: "Voz del oficio" },
  { t: "El mercado no tiene memoria: cada llamada es una oportunidad nueva.", a: "Voz del oficio" },
  { t: "El buen agente no busca la casa perfecta: busca la casa correcta para esa familia.", a: "Voz del oficio" },
  // — Negocios y persistencia —
  { t: "El éxito no es definitivo, el fracaso no es fatal: lo que cuenta es el coraje para continuar.", a: "Winston Churchill" },
  { t: "La única forma de hacer un gran trabajo es amar lo que haces.", a: "Steve Jobs" },
  { t: "No te preocupes por el fracaso; preocúpate por las oportunidades que pierdes cuando ni siquiera lo intentas.", a: "Jack Canfield" },
  { t: "El mercado siempre puede permanecer irracional más tiempo del que tú puedes permanecer solvente.", a: "John Maynard Keynes" },
  { t: "La oportunidad no toca: presenta su tarjeta cuando vienes a buscarla.", a: "Charles Schwab" },
  { t: "Quien quiere hacer algo encuentra un medio; quien no quiere hacer nada encuentra una excusa.", a: "Proverbio árabe" },
  { t: "El que no arriesga, no gana.", a: "Refrán popular" },
  { t: "Cada batalla se gana antes de pelearla.", a: "Sun Tzu" },
  { t: "No vendemos casas. Vendemos sueños, posibilidades, hogares.", a: "Barbara Corcoran" },
  { t: "El dinero es como el estiércol: solo sirve si lo esparces.", a: "J. Paul Getty" },
  { t: "Lo importante no es lo que te pasa, sino cómo reaccionas a lo que te pasa.", a: "Epicteto" },
  { t: "Si no estás dispuesto a arriesgarlo todo, no esperes lograr nada.", a: "Muhammad Ali" },
  { t: "En los negocios, lo que es peligroso es no evolucionar.", a: "Jeff Bezos" },
  { t: "El precio es lo que pagas. El valor es lo que recibes.", a: "Warren Buffett" },
  { t: "No se trata de ideas. Se trata de hacer que las ideas sucedan.", a: "Scott Belsky" },
  { t: "Si lo construyes, ellos vendrán.", a: "Field of Dreams" },
  { t: "La codicia, a falta de una mejor palabra, es buena.", a: "Wall Street — Gordon Gekko" },
  { t: "Siempre estar cerrando.", a: "Glengarry Glen Ross" },
  { t: "Café es para closers.", a: "Glengarry Glen Ross" },
  { t: "La gente no compra productos: compra la versión mejor de sí misma.", a: "Don Draper — Mad Men" },
  { t: "El que tiene un porqué para vivir, puede soportar casi cualquier cómo.", a: "Friedrich Nietzsche" },
  { t: "Lo que hagas hoy puede mejorar todos tus mañanas.", a: "Ralph Marston" },
  { t: "El verdadero valor de un hombre se determina principalmente examinando en qué medida ha alcanzado la liberación del yo.", a: "Albert Einstein" },
  { t: "No persigas el éxito: vuélvete una persona de valor y el éxito te seguirá.", a: "Albert Einstein" },
];
