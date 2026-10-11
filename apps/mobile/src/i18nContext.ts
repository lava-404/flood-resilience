import { createContext, useContext } from 'react';
import { t as tr, type Key, type Lang } from './core/i18n.ts';
export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: 'en', setLang: () => {} });
export const useT = () => { const { lang } = useContext(LangContext); return (k: Key, p?: Record<string, string | number>) => tr(lang, k, p); };
