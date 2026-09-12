import { getLanguage } from "./index";
const copy = {
  career: ["La carriera", "The career", "La carrera"],
  season: ["Stagioni", "Seasons", "Temporadas"],
  club: ["Club / campionato", "Club / competition", "Club / competición"],
  apps: ["Pres. (gol)", "Apps (goals)", "Part. (goles)"],
  loan: ["Prestito", "Loan", "Cesión"],
  who: [
    "Chi è il calciatore?",
    "Who is the player?",
    "¿Quién es el futbolista?",
  ],
  follow: [
    "Segui i club. Ricostruisci la carriera.",
    "Follow the clubs. Trace the career.",
    "Sigue los clubes. Reconstruye la carrera.",
  ],
  answer: ["La tua risposta", "Your answer", "Tu respuesta"],
  archive: ["Archivio", "Archive", "Archivo"],
  more: ["Assistenza e privacy", "Support and privacy", "Ayuda y privacidad"],
  reports: ["Segnalazioni", "Report a problem", "Notificar un problema"],
  refunds: [
    "Rimborsi e acquisti",
    "Refunds and purchases",
    "Reembolsos y compras",
  ],
  privacy: ["Elimina i miei dati", "Delete my data", "Eliminar mis datos"],
  backArena: ["Arena", "Arena", "Arena"],
  backProfile: ["Profilo", "Profile", "Perfil"],
  backDaily: ["Torna alla Daily", "Back to Daily", "Volver a Daily"],
  shop: ["Shop", "Shop", "Tienda"],
  referral: ["Invita amici", "Invite friends", "Invita amigos"],
  events: ["Eventi", "Events", "Eventos"],
  preview: [
    "Anteprima · dati di esempio",
    "Preview · sample data",
    "Vista previa · datos de ejemplo",
  ],
  previewNote: [
    "Questa modalità non è ancora disponibile in V2.",
    "This mode is not available in V2 yet.",
    "Este modo aún no está disponible en V2.",
  ],
  final: ["Fischio finale", "Full time", "Final del partido"],
  next: [
    "La prossima carriera ti aspetta domani.",
    "The next career arrives tomorrow.",
    "La próxima carrera llega mañana.",
  ],
  missing: [
    "Carriera non disponibile",
    "Career unavailable",
    "Carrera no disponible",
  ],
  wait: [
    "In attesa del calcio d’inizio",
    "Waiting for kick-off",
    "Esperando el inicio",
  ],
  connection: [
    "La partita può aspettare",
    "The game can wait",
    "El partido puede esperar",
  ],
  points: ["Punti in palio", "Points available", "Puntos en juego"],
} as const;
export function v(key: keyof typeof copy): string {
  return copy[key][({ it: 0, en: 1, es: 2 } as const)[getLanguage()]];
}
