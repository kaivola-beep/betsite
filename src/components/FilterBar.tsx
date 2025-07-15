import React, { useState } from 'react';
import { Filter, ChevronDown, X, CheckCircle, AlertTriangle } from 'lucide-react';
import { useBonusContext } from '../context/BonusContext';

const FilterBar = () => {
  const { filters, setFilters } = useBonusContext();
  const [showFilters, setShowFilters] = useState(false);
  const [showActiveOnly, setShowActiveOnly] = useState(true);

  const bonusTypes = [
    { value: 'signup', label: 'Sign-up Bonus' },
    { value: 'cashback', label: 'Cashback' },
    { value: 'free-spins', label: 'Free Spins' },
    { value: 'reload', label: 'Reload Bonus' }
  ];

  const wageringRequirements = [
    { value: 'none', label: 'No Wagering' },
    { value: 'low', label: 'Low (≤35x)' },
    { value: 'medium', label: 'Medium (36-45x)' },
    { value: 'high', label: 'High (>45x)' }
  ];

  const countries = [
    { value: 'US', label: 'United States' },
    { value: 'UK', label: 'United Kingdom' },
    { value: 'CA', label: 'Canada' },
    { value: 'AU', label: 'Australia' },
    { value: 'DE', label: 'Germany' },
    { value: 'SE', label: 'Sweden' }
  ];

  const sortOptions = [
    { value: 'popularity', label: 'Most Popular' },
    { value: 'value', label: 'Highest Value' },
    { value: 'rating', label: 'Best Rated' }
  ];

  const handleFilterChange = (filterType: keyof typeof filters, value: string) => {
    if (filterType === 'sortBy') {
      setFilters({ ...filters, [filterType]: value as any });
    } else {
      const currentValues = filters[filterType] as string[];
      const newValues = currentValues.includes(value)
        ? currentValues.filter(v => v !== value)
        : [...currentValues, value];
      setFilters({ ...filters, [filterType]: newValues });
    }
  };

  const clearFilters = () => {
    setFilters({
      bonusType: [],
      wageringRequirement: [],
      countries: [],
      sortBy: 'popularity'
    });
  };

  const activeFilterCount = filters.bonusType.length + filters.wageringRequirement.length + filters.countries.length;

  return (
    <div className="mb-8">
      {/* Filter Toggle Button - Mobile */}
      <div className="md:hidden mb-4">
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center space-x-2 bg-white border border-slate-300 rounded-lg px-4 py-2 w-full justify-between"
        >
          <div className="flex items-center space-x-2">
            <Filter size={20} className="text-slate-600" />
            <span className="font-medium">Filters</span>
            {activeFilterCount > 0 && (
              <span className="bg-emerald-100 text-emerald-800 text-xs px-2 py-1 rounded-full">
                {activeFilterCount}
              </span>
            )}
          </div>
          <ChevronDown className={`transform transition-transform ${showFilters ? 'rotate-180' : ''}`} size={20} />
        </button>
      </div>

      {/* Filter Panel */}
      <div className={`bg-white rounded-lg border border-slate-200 p-6 ${showFilters || 'hidden md:block'}`}>
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-slate-900">Filter Bonuses</h3>
          {(activeFilterCount > 0 || !showActiveOnly) && (
            <button
              onClick={clearFilters}
              className="flex items-center space-x-1 text-emerald-600 hover:text-emerald-700 text-sm font-medium"
            >
              <X size={16} />
              <span>Clear all</span>
            </button>
          )}
        </div>

        {/* Active Status Filter */}
        <div className="mb-6 p-4 bg-slate-50 rounded-lg">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <CheckCircle className="text-emerald-600" size={20} />
              <div>
                <h4 className="font-medium text-slate-900">Show Active Bonuses Only</h4>
                <p className="text-sm text-slate-600">Hide expired or inactive offers</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={showActiveOnly}
                onChange={(e) => setShowActiveOnly(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-emerald-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
            </label>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {/* Bonus Type */}
          <div>
            <h4 className="font-medium text-slate-900 mb-3">Bonus Type</h4>
            <div className="space-y-2">
              {bonusTypes.map(type => (
                <label key={type.value} className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={filters.bonusType.includes(type.value)}
                    onChange={() => handleFilterChange('bonusType', type.value)}
                    className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="text-sm text-slate-700">{type.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Wagering Requirements */}
          <div>
            <h4 className="font-medium text-slate-900 mb-3">Wagering</h4>
            <div className="space-y-2">
              {wageringRequirements.map(req => (
                <label key={req.value} className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={filters.wageringRequirement.includes(req.value)}
                    onChange={() => handleFilterChange('wageringRequirement', req.value)}
                    className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="text-sm text-slate-700">{req.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Countries */}
          <div>
            <h4 className="font-medium text-slate-900 mb-3">Available In</h4>
            <div className="space-y-2">
              {countries.map(country => (
                <label key={country.value} className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={filters.countries.includes(country.value)}
                    onChange={() => handleFilterChange('countries', country.value)}
                    className="rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="text-sm text-slate-700">{country.label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Sort By */}
          <div>
            <h4 className="font-medium text-slate-900 mb-3">Sort By</h4>
            <div className="space-y-2">
              {sortOptions.map(option => (
                <label key={option.value} className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="radio"
                    name="sortBy"
                    checked={filters.sortBy === option.value}
                    onChange={() => handleFilterChange('sortBy', option.value)}
                    className="border-slate-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="text-sm text-slate-700">{option.label}</span>
                </label>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FilterBar