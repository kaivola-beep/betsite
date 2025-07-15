import React from 'react';
import { BookmarkCheck, Trash2, ExternalLink, Calendar, TrendingUp } from 'lucide-react';
import { useBonusContext } from '../context/BonusContext';
import BonusCard from './BonusCard';

const BonusTracker = () => {
  const { getSavedBonuses, savedBonuses, toggleSavedBonus } = useBonusContext();
  const savedBonusList = getSavedBonuses();

  if (savedBonusList.length === 0) {
    return (
      <div className="text-center py-16">
        <div className="text-6xl mb-6">📋</div>
        <h2 className="text-2xl font-bold text-slate-900 mb-4">Your Bonus Tracker is Empty</h2>
        <p className="text-slate-600 mb-8 max-w-md mx-auto">
          Start saving bonuses you're interested in to keep track of them here. 
          Click the bookmark icon on any bonus card to add it to your tracker.
        </p>
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-6 max-w-md mx-auto">
          <div className="flex items-center space-x-3 mb-3">
            <BookmarkCheck className="text-emerald-600" size={24} />
            <h3 className="font-semibold text-emerald-900">Pro Tip</h3>
          </div>
          <p className="text-emerald-800 text-sm">
            Save bonuses to compare them later, track expiration dates, and never miss out on great deals!
          </p>
        </div>
      </div>
    );
  }

  const totalBonusValue = savedBonusList.reduce((sum, bonus) => sum + bonus.bonusValue, 0);
  const averageRating = savedBonusList.reduce((sum, bonus) => sum + bonus.rating, 0) / savedBonusList.length;

  return (
    <div>
      {/* Header Stats */}
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-slate-900 mb-6">My Bonus Tracker</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-lg border border-slate-200 p-6">
            <div className="flex items-center space-x-3 mb-2">
              <BookmarkCheck className="text-emerald-600" size={24} />
              <h3 className="font-semibold text-slate-900">Saved Bonuses</h3>
            </div>
            <div className="text-3xl font-bold text-slate-900">{savedBonusList.length}</div>
            <div className="text-sm text-slate-600">Ready to claim</div>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 p-6">
            <div className="flex items-center space-x-3 mb-2">
              <TrendingUp className="text-emerald-600" size={24} />
              <h3 className="font-semibold text-slate-900">Total Value</h3>
            </div>
            <div className="text-3xl font-bold text-slate-900">${totalBonusValue.toLocaleString()}</div>
            <div className="text-sm text-slate-600">Potential bonus value</div>
          </div>

          <div className="bg-white rounded-lg border border-slate-200 p-6">
            <div className="flex items-center space-x-3 mb-2">
              <Calendar className="text-emerald-600" size={24} />
              <h3 className="font-semibold text-slate-900">Avg Rating</h3>
            </div>
            <div className="text-3xl font-bold text-slate-900">{averageRating.toFixed(1)}</div>
            <div className="text-sm text-slate-600">Quality score</div>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-slate-50 rounded-lg p-6 mb-8">
        <h3 className="font-semibold text-slate-900 mb-4">Quick Actions</h3>
        <div className="flex flex-wrap gap-3">
          <button className="flex items-center space-x-2 bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 transition-colors">
            <ExternalLink size={16} />
            <span>Claim All Bonuses</span>
          </button>
          <button className="flex items-center space-x-2 bg-white border border-slate-300 text-slate-700 px-4 py-2 rounded-lg hover:bg-slate-50 transition-colors">
            <Calendar size={16} />
            <span>Sort by Expiry</span>
          </button>
          <button 
            onClick={() => savedBonuses.forEach(id => toggleSavedBonus(id))}
            className="flex items-center space-x-2 bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded-lg hover:bg-red-100 transition-colors"
          >
            <Trash2 size={16} />
            <span>Clear All</span>
          </button>
        </div>
      </div>

      {/* Saved Bonuses Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {savedBonusList.map(bonus => (
          <BonusCard key={bonus.id} bonus={bonus} />
        ))}
      </div>
    </div>
  );
};

export default BonusTracker