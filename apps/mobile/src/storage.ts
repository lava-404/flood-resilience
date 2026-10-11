import AsyncStorage from '@react-native-async-storage/async-storage';
import type { Persist, Rec } from './core/store.ts';
import type { CachedRisk } from './core/cache.ts';
import type { Lang } from './core/i18n.ts';

export const messagePersist: Persist = {
  load: async () => JSON.parse((await AsyncStorage.getItem('fr.messages')) ?? '[]') as Rec[],
  save: (rows) => AsyncStorage.setItem('fr.messages', JSON.stringify(rows)),
};
export const saveRiskCache = (c: CachedRisk & { response: any }) => AsyncStorage.setItem('fr.risk', JSON.stringify(c));
export const loadRiskCache = async (): Promise<(CachedRisk & { response: any }) | null> => JSON.parse((await AsyncStorage.getItem('fr.risk')) ?? 'null');
export const savePrefs = (p: { lang: Lang; lat: number; lon: number; useGps: boolean }) => AsyncStorage.setItem('fr.prefs', JSON.stringify(p));
export const loadPrefs = async () => JSON.parse((await AsyncStorage.getItem('fr.prefs')) ?? 'null');
export const saveJson = (k: string, v: unknown) => AsyncStorage.setItem('fr.' + k, JSON.stringify(v));
export const loadJson = async <T,>(k: string): Promise<T | null> => JSON.parse((await AsyncStorage.getItem('fr.' + k)) ?? 'null');
