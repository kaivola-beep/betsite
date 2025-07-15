import React, { useState } from 'react';
import Header from './components/Header';
import FilterBar from './components/FilterBar';
import BonusGrid from './components/BonusGrid';
import BonusTracker from './components/BonusTracker';
import CasinoQuiz from './components/CasinoQuiz';
import Footer from './components/Footer';
import { BonusProvider } from './context/BonusContext';

function App() {
  const [activeTab, setActiveTab] = useState<'bonuses' | 'tracker' | 'quiz'>('bonuses');

  return (
    <BonusProvider>
      <div className="min-h-screen bg-slate-50">
        <Header />
        
        {/* Navigation Tabs */}
        <div className="sticky top-0 z-40 bg-white border-b border-slate-200 shadow-sm">
          <div className="max-w-7xl mx-auto px-4">
            <nav className="flex space-x-8">
              <button
                onClick={() => setActiveTab('bonuses')}
                className={`py-4 px-2 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === 'bonuses'
                    ? 'border-emerald-500 text-emerald-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                Casino Bonuses
              </button>
              <button
                onClick={() => setActiveTab('tracker')}
                className={`py-4 px-2 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === 'tracker'
                    ? 'border-emerald-500 text-emerald-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                My Tracker
              </button>
              <button
                onClick={() => setActiveTab('quiz')}
                className={`py-4 px-2 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === 'quiz'
                    ? 'border-emerald-500 text-emerald-600'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}
              >
                Casino Finder
              </button>
            </nav>
          </div>
        </div>

        <main className="max-w-7xl mx-auto px-4 py-8">
          {activeTab === 'bonuses' && (
            <>
              <FilterBar />
              <BonusGrid />
            </>
          )}
          {activeTab === 'tracker' && <BonusTracker />}
          {activeTab === 'quiz' && <CasinoQuiz />}
        </main>

        <Footer />
      </div>
    </BonusProvider>
  );
}

export default App;