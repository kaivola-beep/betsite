import React, { useState } from 'react';
import Header from './components/Header';
import FilterBar from './components/FilterBar';
import BonusGrid from './components/BonusGrid';
import BonusTracker from './components/BonusTracker';
import CasinoQuiz from './components/CasinoQuiz';
import Footer from './components/Footer';
import ErrorBoundary from './components/ErrorBoundary';
import { BonusProvider } from './context/BonusContext';

function App() {
  const [activeTab, setActiveTab] = useState<'bonuses' | 'tracker' | 'quiz'>('bonuses');

  return (
    <ErrorBoundary>
      <BonusProvider>
        <div className="min-h-screen bg-slate-50">
          <Header />
          
          {/* Navigation Tabs */}
          <div className="sticky top-0 z-40 bg-white border-b border-slate-200 shadow-sm">
            <div className="max-w-7xl mx-auto px-4">
              <nav className="flex space-x-8" aria-label="Main navigation" role="navigation">
                <div role="tablist" aria-label="Main Tabs" className="flex space-x-8 w-full">
                  <button
                    role="tab"
                    aria-selected={activeTab === 'bonuses'}
                    aria-controls="tab-panel-bonuses"
                    id="tab-bonuses"
                    tabIndex={activeTab === 'bonuses' ? 0 : -1}
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
                    role="tab"
                    aria-selected={activeTab === 'tracker'}
                    aria-controls="tab-panel-tracker"
                    id="tab-tracker"
                    tabIndex={activeTab === 'tracker' ? 0 : -1}
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
                    role="tab"
                    aria-selected={activeTab === 'quiz'}
                    aria-controls="tab-panel-quiz"
                    id="tab-quiz"
                    tabIndex={activeTab === 'quiz' ? 0 : -1}
                    onClick={() => setActiveTab('quiz')}
                    className={`py-4 px-2 border-b-2 font-medium text-sm transition-colors ${
                      activeTab === 'quiz'
                        ? 'border-emerald-500 text-emerald-600'
                        : 'border-transparent text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    Casino Finder
                  </button>
                </div>
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
    </ErrorBoundary>
  );
}

export default App;