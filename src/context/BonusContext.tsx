import React, { createContext, useContext, useState, ReactNode } from 'react';

export interface Bonus {
  id: string;
  casinoName: string;
  bonusOffer: string;
  bonusValue: number;
  bonusType: 'signup' | 'cashback' | 'free-spins' | 'reload';
  wageringRequirement: 'none' | 'low' | 'medium' | 'high';
  wageringMultiplier: number;
  countries: string[];
  features: string[];
  rating: number;
  popularity: number;
  description: string;
  terms: string[];
  logo: string;
  isActive: boolean;
  lastVerified: Date;
  expiresAt?: Date;
  minDeposit: number;
  maxCashout?: number;
  gameContribution: {
    slots: number;
    tableGames: number;
    liveDealer: number;
  };
}

export interface Filters {
  bonusType: string[];
  wageringRequirement: string[];
  countries: string[];
  sortBy: 'value' | 'popularity' | 'rating';
}

interface BonusContextType {
  bonuses: Bonus[];
  savedBonuses: string[];
  filters: Filters;
  setFilters: (filters: Filters) => void;
  toggleSavedBonus: (bonusId: string) => void;
  getSavedBonuses: () => Bonus[];
}

const BonusContext = createContext<BonusContextType | undefined>(undefined);

const mockBonuses: Bonus[] = [
  {
    id: '1',
    casinoName: 'CryptoSlots Casino',
    bonusOffer: '200% up to $2,000 + 50 Free Spins',
    bonusValue: 2000,
    bonusType: 'signup',
    wageringRequirement: 'low',
    wageringMultiplier: 35,
    countries: ['US', 'CA', 'UK', 'AU'],
    features: ['Crypto accepted', 'No KYC', 'Instant withdrawals'],
    rating: 4.8,
    popularity: 95,
    description: 'Welcome bonus for new players with crypto deposits',
    terms: ['35x wagering requirement', 'Valid for 30 days', 'Min deposit $20'],
    logo: '🎰',
    isActive: true,
    lastVerified: new Date(Date.now() - 2 * 60 * 60 * 1000), // 2 hours ago
    expiresAt: new Date(Date.now() + 25 * 24 * 60 * 60 * 1000), // 25 days from now
    minDeposit: 20,
    maxCashout: 10000,
    gameContribution: {
      slots: 100,
      tableGames: 10,
      liveDealer: 10
    }
  },
  {
    id: '2',
    casinoName: 'Royal Spin Palace',
    bonusOffer: '100% up to $1,500 + 100 Free Spins',
    bonusValue: 1500,
    bonusType: 'signup',
    wageringRequirement: 'medium',
    wageringMultiplier: 40,
    countries: ['UK', 'CA', 'DE', 'SE'],
    features: ['Live dealer games', 'Mobile optimized', 'VIP program'],
    rating: 4.6,
    popularity: 88,
    description: 'Premium welcome package with live casino access',
    terms: ['40x wagering requirement', 'Valid for 21 days', 'Min deposit $25'],
    logo: '👑',
    isActive: true,
    lastVerified: new Date(Date.now() - 30 * 60 * 1000), // 30 minutes ago
    expiresAt: new Date(Date.now() + 18 * 24 * 60 * 60 * 1000), // 18 days from now
    minDeposit: 25,
    maxCashout: 7500,
    gameContribution: {
      slots: 100,
      tableGames: 20,
      liveDealer: 20
    }
  },
  {
    id: '3',
    casinoName: 'Lightning Casino',
    bonusOffer: '25% Cashback up to $500',
    bonusValue: 500,
    bonusType: 'cashback',
    wageringRequirement: 'none',
    wageringMultiplier: 0,
    countries: ['US', 'CA', 'UK', 'AU', 'NZ'],
    features: ['No wagering', 'Weekly cashback', 'Fast payouts'],
    rating: 4.9,
    popularity: 92,
    description: 'Weekly cashback with no wagering requirements',
    terms: ['No wagering requirement', 'Paid weekly', 'Min cashback $10'],
    logo: '⚡',
    isActive: true,
    lastVerified: new Date(Date.now() - 15 * 60 * 1000), // 15 minutes ago
    minDeposit: 0,
    gameContribution: {
      slots: 100,
      tableGames: 100,
      liveDealer: 100
    }
  },
  {
    id: '4',
    casinoName: 'Mega Spins Casino',
    bonusOffer: '500 Free Spins on Starburst',
    bonusValue: 250,
    bonusType: 'free-spins',
    wageringRequirement: 'low',
    wageringMultiplier: 30,
    countries: ['UK', 'DE', 'SE', 'NO'],
    features: ['Popular slots', 'Mobile app', 'Daily bonuses'],
    rating: 4.4,
    popularity: 76,
    description: 'Massive free spins package for slot enthusiasts',
    terms: ['30x wagering requirement', 'Valid for 7 days', 'Max win $100'],
    logo: '🎡',
    isActive: false,
    lastVerified: new Date(Date.now() - 6 * 60 * 60 * 1000), // 6 hours ago
    expiresAt: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000), // 2 days from now
    minDeposit: 10,
    maxCashout: 100,
    gameContribution: {
      slots: 100,
      tableGames: 0,
      liveDealer: 0
    }
  },
  {
    id: '5',
    casinoName: 'Bitcoin Blackjack',
    bonusOffer: '150% up to 3 BTC',
    bonusValue: 3000,
    bonusType: 'signup',
    wageringRequirement: 'medium',
    wageringMultiplier: 35,
    countries: ['US', 'CA', 'UK', 'AU', 'DE'],
    features: ['Bitcoin only', 'Provably fair', 'Anonymous play'],
    rating: 4.7,
    popularity: 84,
    description: 'Cryptocurrency-focused casino with provably fair games',
    terms: ['35x wagering requirement', 'Valid for 14 days', 'Min deposit 0.001 BTC'],
    logo: '₿',
    isActive: true,
    lastVerified: new Date(Date.now() - 45 * 60 * 1000), // 45 minutes ago
    expiresAt: new Date(Date.now() + 12 * 24 * 60 * 60 * 1000), // 12 days from now
    minDeposit: 50, // ~0.001 BTC
    maxCashout: 15000,
    gameContribution: {
      slots: 100,
      tableGames: 25,
      liveDealer: 25
    }
  },
  {
    id: '6',
    casinoName: 'Lucky Stars Casino',
    bonusOffer: '50% Reload Bonus up to $1,000',
    bonusValue: 1000,
    bonusType: 'reload',
    wageringRequirement: 'high',
    wageringMultiplier: 45,
    countries: ['CA', 'UK', 'AU', 'NZ'],
    features: ['Weekly reload', 'Loyalty points', 'Tournament access'],
    rating: 4.3,
    popularity: 71,
    description: 'Weekly reload bonus for existing players',
    terms: ['45x wagering requirement', 'Valid for 7 days', 'Min deposit $50'],
    logo: '⭐',
    isActive: true,
    lastVerified: new Date(Date.now() - 3 * 60 * 60 * 1000), // 3 hours ago
    expiresAt: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000), // 5 days from now
    minDeposit: 50,
    maxCashout: 5000,
    gameContribution: {
      slots: 100,
      tableGames: 15,
      liveDealer: 15
    }
  }
];

export const BonusProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [savedBonuses, setSavedBonuses] = useState<string[]>([]);
  const [filters, setFilters] = useState<Filters>({
    bonusType: [],
    wageringRequirement: [],
    countries: [],
    sortBy: 'popularity'
  });

  const toggleSavedBonus = (bonusId: string) => {
    setSavedBonuses(prev => 
      prev.includes(bonusId) 
        ? prev.filter(id => id !== bonusId)
        : [...prev, bonusId]
    );
  };

  const getSavedBonuses = () => {
    return mockBonuses.filter(bonus => savedBonuses.includes(bonus.id));
  };

  return (
    <BonusContext.Provider value={{
      bonuses: mockBonuses,
      savedBonuses,
      filters,
      setFilters,
      toggleSavedBonus,
      getSavedBonuses
    }}>
      {children}
    </BonusContext.Provider>
  );
};

export const useBonusContext = () => {
  const context = useContext(BonusContext);
  if (context === undefined) {
    throw new Error('useBonusContext must be used within a BonusProvider');
  }
  return context;
};