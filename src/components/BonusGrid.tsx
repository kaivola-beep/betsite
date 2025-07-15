import React, { useMemo } from 'react';
import BonusCard from './BonusCard';
import { useBonusContext } from '../context/BonusContext';

const MemoizedBonusCard = React.memo(BonusCard);

const BonusGrid = () => {
  const { bonuses, filters } = useBonusContext();

  // Memoize filtered bonuses
  const filteredBonuses = useMemo(() =>
    bonuses.filter((bonus: any) => {
      // Filter by bonus type
      if (filters.bonusType.length > 0 && !filters.bonusType.includes(bonus.bonusType)) {
        return false;
      }
      // Filter by wagering requirement
      if (filters.wageringRequirement.length > 0 && !filters.wageringRequirement.includes(bonus.wageringRequirement)) {
        return false;
      }
      // Filter by countries
      if (filters.countries.length > 0) {
        const hasMatchingCountry = filters.countries.some((country: string) => 
          bonus.countries.includes(country)
        );
        if (!hasMatchingCountry) return false;
      }
      return true;
    }),
    [bonuses, filters.bonusType, filters.wageringRequirement, filters.countries]
  );

  // Memoize sorted bonuses
  const sortedBonuses = useMemo(() => {
    return [...filteredBonuses].sort((a, b) => {
      switch (filters.sortBy) {
        case 'value':
          return b.bonusValue - a.bonusValue;
        case 'rating':
          return b.rating - a.rating;
        case 'popularity':
        default:
          return b.popularity - a.popularity;
      }
    });
  }, [filteredBonuses, filters.sortBy]);

  if (sortedBonuses.length === 0) {
    return (
      <div className="text-center py-16">
        <div className="text-6xl mb-4">🎰</div>
        <h3 className="text-xl font-semibold text-slate-900 mb-2">No bonuses found</h3>
        <p className="text-slate-600">Try adjusting your filters to see more results.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-slate-900">
          Casino Bonuses ({sortedBonuses.length})
        </h2>
        <div className="text-sm text-slate-600">
          Sorted by {filters.sortBy === 'value' ? 'highest value' : filters.sortBy === 'rating' ? 'best rated' : 'most popular'}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {sortedBonuses.map(bonus => (
          <MemoizedBonusCard key={bonus.id} bonus={bonus} />
        ))}
      </div>
    </div>
  );
};

export default BonusGrid;