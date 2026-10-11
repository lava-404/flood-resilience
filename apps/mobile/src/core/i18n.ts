// English + Hindi. Hindi strings are a first draft and NEED REVIEW BY A NATIVE SPEAKER before any public release.
// Wording rule (SRS 14.1): no "guaranteed"/"will flood", no numeric probabilities.
export type Lang = 'en' | 'hi';
export const STRINGS = {
  en: {
    'state.SAFE': 'SAFE', 'state.WATCH': 'WATCH', 'state.WARNING': 'WARNING', 'state.EVACUATE': 'EVACUATE',
    'action.SAFE': 'No flood risk indicated right now. Keep checking for updates.',
    'action.WATCH': 'Flood risk may be increasing. Get ready.',
    'action.WARNING': 'Your area is likely to be affected. Prepare to move.',
    'action.EVACUATE': 'Move to higher ground or a shelter and follow official instructions.',
    'confidence.low': 'Confidence: low', 'confidence.medium': 'Confidence: medium', 'confidence.high': 'Confidence: high',
    'updated.minutes': 'Updated {n} min ago', 'official.active': 'Official warning active',
    'status.live': 'Live', 'status.cached': 'Saved information', 'status.expired': 'Out of date', 'status.none': 'No data yet',
    'offline.banner': 'No internet. Showing saved information from {n} min ago.',
    'demo.notice': 'Demo data. Not real observations.',
    'why': 'Why?', 'whatToDo': 'What should I do?',
    'sos.title': 'Emergency SOS', 'sos.send': 'Send SOS', 'sos.people': 'People with you', 'sos.medical': 'Medical help needed',
    'sos.note': 'Short note (optional)',
    'delivery.queued': 'Saved on this phone', 'delivery.relayed': 'Passed to a nearby phone',
    'delivery.delivered': 'Received by responders', 'delivery.acknowledged': 'Responders acknowledged',
    'peers.count': '{n} nearby device(s)', 'peers.none': 'No nearby devices found yet',
    'settings.language': 'Language', 'settings.location': 'Use my location',
    'reports.title': 'Nearby reports', 'reports.unverified': 'Unverified',
  },
  hi: {
    'state.SAFE': 'सुरक्षित', 'state.WATCH': 'निगरानी रखें', 'state.WARNING': 'चेतावनी', 'state.EVACUATE': 'स्थान खाली करें',
    'action.SAFE': 'अभी बाढ़ का जोखिम नहीं दिख रहा। अपडेट देखते रहें।',
    'action.WATCH': 'बाढ़ का जोखिम बढ़ सकता है। तैयार रहें।',
    'action.WARNING': 'आपके क्षेत्र पर असर पड़ने की संभावना है। निकलने की तैयारी करें।',
    'action.EVACUATE': 'ऊँची जगह या आश्रय स्थल पर जाएँ और अधिकारियों के निर्देश मानें।',
    'confidence.low': 'भरोसा: कम', 'confidence.medium': 'भरोसा: मध्यम', 'confidence.high': 'भरोसा: अधिक',
    'updated.minutes': '{n} मिनट पहले अपडेट हुआ', 'official.active': 'आधिकारिक चेतावनी जारी है',
    'status.live': 'लाइव', 'status.cached': 'सहेजी हुई जानकारी', 'status.expired': 'पुरानी जानकारी', 'status.none': 'अभी कोई डेटा नहीं',
    'offline.banner': 'इंटरनेट नहीं है। {n} मिनट पहले की सहेजी हुई जानकारी दिखाई जा रही है।',
    'demo.notice': 'डेमो डेटा। वास्तविक अवलोकन नहीं।',
    'why': 'क्यों?', 'whatToDo': 'मुझे क्या करना चाहिए?',
    'sos.title': 'आपातकालीन SOS', 'sos.send': 'SOS भेजें', 'sos.people': 'आपके साथ कितने लोग', 'sos.medical': 'चिकित्सा सहायता चाहिए',
    'sos.note': 'छोटा संदेश (वैकल्पिक)',
    'delivery.queued': 'इस फ़ोन में सहेजा गया', 'delivery.relayed': 'पास के फ़ोन तक पहुँचा',
    'delivery.delivered': 'बचाव दल को मिल गया', 'delivery.acknowledged': 'बचाव दल ने पुष्टि की',
    'peers.count': 'पास के {n} उपकरण', 'peers.none': 'अभी कोई पास का उपकरण नहीं मिला',
    'settings.language': 'भाषा', 'settings.location': 'मेरा स्थान उपयोग करें',
    'reports.title': 'आस-पास की रिपोर्टें', 'reports.unverified': 'अपुष्ट',
  },
} as const;
export type Key = keyof typeof STRINGS.en;

export function t(lang: Lang, key: Key, params: Record<string, string | number> = {}): string {
  const s: string = STRINGS[lang][key] ?? STRINGS.en[key];
  return s.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? ''));
}
