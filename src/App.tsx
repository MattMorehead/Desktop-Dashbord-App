import { useEffect, useState } from 'react';
import { listen } from '@tauri-apps/api/event';
import { invoke } from '@tauri-apps/api/core';
import { ShieldAlert } from 'lucide-react';

interface DashboardState {
  location: { city: string; region: string };
  weather: { temperature: string; wmo_code: number; updated_at: string; alert?: string; condition?: string; icon?: string; high?: string; low?: string };
  markets: { indices: Array<{ ticker: string; symbol: string; value: string; change: string; trend: 'up' | 'down' }>; movers?: Array<{ ticker: string; symbol: string; value: string; change: string; trend: 'up' | 'down' }> };
  news: { world: Array<{ title: string; source: string; url: string; is_breaking: boolean }>; national: Array<{ title: string; source: string; url: string; is_breaking: boolean }>; local: Array<{ title: string; source: string; url: string; is_breaking: boolean }> };
}

// Helper to sort breaking news first
const sortNews = (news: Array<{ title: string; source: string; url: string; is_breaking: boolean }> = []) => {
  return [...news].sort((a, b) => (a.is_breaking === b.is_breaking ? 0 : a.is_breaking ? -1 : 1));
};

export default function App() {
  const [state, setState] = useState<DashboardState | null>(null);
  const [currentTime, setCurrentTime] = useState<string>('--:-- --');

  // Independent autonomous clock
  useEffect(() => {
    const updateTime = () => {
      setCurrentTime(new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const unlisten = listen<string>('agent-state', (event) => {
      try {
        const parsed = JSON.parse(event.payload);
        setState(parsed);
      } catch (err) {
        console.error("Failed to parse agent state", err);
      }
    });
    return () => { unlisten.then(f => f()); };
  }, []);

  const openLink = (url: string) => {
    if (url) invoke('open_external_url', { url });
  };

  return (
    <div className="min-h-screen bg-[#262626] text-[#F5F5F5] p-5 font-sans select-none flex flex-col gap-4">
      {/* Header Bar */}
      <header className="flex justify-between items-baseline px-1 text-[#F5F5F5]">
        <div className="text-xl md:text-2xl font-semibold">
          {state?.location?.city ? `${state.location.city}, ${state.location.region}` : 'Locating...'}
        </div>
        <div className="text-xl md:text-2xl font-semibold">{currentTime}</div>
      </header>

      {/* Top Row: Weather & Markets */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Weather Card */}
        <div className="bg-[#1C1C1C] border border-[#383838] rounded-2xl p-5 shadow-lg flex flex-col justify-between min-h-[180px]">
          <span className="text-xs uppercase tracking-wider text-[#A3A3A3] font-semibold mb-2 block">Weather</span>
          <div className="grid grid-cols-2 items-center h-full flex-1">
            <div className="flex flex-col justify-center h-full">
              <div className="text-6xl md:text-7xl font-bold leading-none tracking-tight">{state?.weather?.temperature || '--°'}</div>
              <div className="text-base text-[#A3A3A3] mt-3 font-medium">{state?.weather?.condition || 'Loading...'}</div>
              <div className="text-sm text-[#737373] mt-1 flex gap-3 font-medium">
                <span>{state?.weather?.high || 'H:--°'}</span>
                <span>{state?.weather?.low || 'L:--°'}</span>
              </div>
            </div>
            <div className="flex justify-end items-center h-full">
              <span 
                className="material-symbols-outlined text-amber-400 select-none drop-shadow-md" 
                style={{ fontSize: '110px', lineHeight: '1', fontVariationSettings: "'FILL' 1" }}
              >
                {state?.weather?.icon || 'partly_cloudy_day'}
              </span>
            </div>
          </div>
          {state?.weather?.alert && (
            <div className="mt-3 bg-red-950/40 border border-[#DC2626] rounded-lg p-2.5 flex items-center gap-2 text-xs text-[#FF3B30]">
              <ShieldAlert className="w-4 h-4 shrink-0" />
              <span>{state.weather.alert}</span>
            </div>
          )}
        </div>

        {/* Markets Card */}
        <div className="bg-[#1C1C1C] border border-[#383838] rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <span className="text-xs uppercase tracking-wider text-[#A3A3A3] font-semibold">Markets</span>
          
          {!state?.markets?.indices?.length ? (
            <div className="flex-1 flex items-center justify-center text-[#737373] text-sm mt-4">
              Market data unavailable
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-2 mt-2">
              {state.markets.indices.map((idx) => (
                <div 
                  key={idx.symbol} 
                  onClick={() => openLink(`https://finance.yahoo.com/quote/${idx.ticker}`)}
                  className="cursor-pointer hover:bg-[#222222] p-2 rounded-lg transition"
                >
                  <div className="text-xs text-[#A3A3A3]">{idx.symbol}</div>
                  <div className="text-sm font-semibold mt-0.5">{idx.value}</div>
                  <div className={`text-xs font-mono font-bold ${idx.trend === 'up' ? 'text-[#00C805]' : 'text-[#FF3B30]'}`}>
                    {idx.trend === 'up' ? '▲' : '▼'} {idx.change}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Movers Marquee */}
          {state?.markets?.movers && state.markets.movers.length > 0 && (
            <div className="mt-4 pt-4 border-t border-[#383838] overflow-hidden pause-on-hover relative w-full group">
              <span className="text-[10px] uppercase text-[#737373] absolute left-0 top-0 bg-[#1C1C1C] pr-2 z-10 font-bold">Top Movers</span>
              <div className="flex w-[200%] animate-marquee mt-4">
                {/* Duplicate the list to create a seamless loop */}
                {[...state.markets.movers, ...state.markets.movers].map((mover, i) => (
                  <div
                    key={`${mover.symbol}-${i}`}
                    onClick={() => openLink(`https://finance.yahoo.com/quote/${mover.ticker}`)}
                    className="flex-shrink-0 cursor-pointer flex items-center gap-2 mx-4 whitespace-nowrap hover:bg-[#222222] px-2 py-1 rounded transition"
                  >
                    <span className="text-xs font-semibold">{mover.symbol}</span>
                    <span className="text-xs">{mover.value}</span>
                    <span className={`text-xs font-mono font-bold ${mover.trend === 'up' ? 'text-[#00C805]' : 'text-[#FF3B30]'}`}>
                      {mover.trend === 'up' ? '▲' : '▼'} {mover.change}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* News Feed Grid */}
      <div className="bg-[#1C1C1C] border border-[#383838] rounded-2xl p-5 shadow-lg flex-1">
        <span className="text-xs uppercase tracking-wider text-[#A3A3A3] font-semibold block mb-3">Headlines</span>
        
        {!state?.news ? (
          <div className="flex-1 flex items-center justify-center text-[#737373] text-sm mt-8">
            Headlines unavailable
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-4">
            {/* Column Render Helper */}
            {[
              { title: 'World', data: state.news.world },
              { title: 'National', data: state.news.national },
              { title: 'Local', data: state.news.local }
            ].map((col) => (
              <div key={col.title} className="space-y-2.5">
                <h3 className="text-[11px] uppercase tracking-wider text-[#737373] mb-3 pb-1 border-b border-[#383838]">{col.title}</h3>
                {col.data && col.data.length > 0 ? sortNews(col.data).map((item, index) => (
                  <div
                    key={index}
                    onClick={() => openLink(item.url)}
                    className="flex items-start gap-3 p-2 rounded-lg hover:bg-[#222222] cursor-pointer transition border border-transparent hover:border-[#383838]"
                  >
                    {item.is_breaking && (
                      <span className="bg-red-950/60 border border-[#DC2626] text-[#FF3B30] text-[9px] font-extrabold px-1.5 py-[1px] rounded tracking-wide shrink-0 mt-0.5">
                        BREAKING
                      </span>
                    )}
                    <span className="text-xs font-medium leading-relaxed flex-1 line-clamp-2">{item.title}</span>
                    <span className="text-[10px] text-[#737373] shrink-0 mt-0.5">{item.source}</span>
                  </div>
                )) : (
                  <div className="text-xs text-[#737373] italic">No {col.title.toLowerCase()} headlines.</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
