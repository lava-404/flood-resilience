import React, { useState } from 'react';
import { Pressable, SafeAreaView, Text, View } from 'react-native';
import { AppProvider, useApp } from './state';
import { LangContext } from './i18nContext';
import { Emergency, Home, MapScreen, Reports, Settings, Timeline } from './screens';

const TABS = { Home, Map: MapScreen, Timeline, SOS: Emergency, Reports, Settings } as const;

function Shell() {
  const [tab, setTab] = useState<keyof typeof TABS>('Home'); const Screen = TABS[tab]; const { lang, setLang } = useApp();
  return (
    <LangContext.Provider value={{ lang, setLang }}>
      <SafeAreaView style={{ flex: 1 }}>
        <View style={{ flex: 1 }}><Screen /></View>
        <View style={{ flexDirection: 'row' }}>{(Object.keys(TABS) as (keyof typeof TABS)[]).map((k) => (
          <Pressable key={k} onPress={() => setTab(k)} accessibilityRole="tab" style={{ flex: 1, padding: 14, backgroundColor: tab === k ? '#1d4ed8' : '#e5e7eb' }}>
            <Text style={{ textAlign: 'center', color: tab === k ? '#fff' : '#111', fontWeight: '700' }}>{k}</Text></Pressable>))}</View>
      </SafeAreaView>
    </LangContext.Provider>);
}
export default function App() { return <AppProvider><Shell /></AppProvider>; }
