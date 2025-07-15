import React from 'react';
import { render, screen } from '@testing-library/react';
import BonusCard from './BonusCard';
import { Bonus } from '../context/BonusContext';
import { BonusProvider } from '../context/BonusContext';

const mockBonus: Bonus = {
  id: '1',
  casinoName: 'Test Casino',
  bonusOffer: '100% up to $100',
  bonusValue: 100,
  bonusType: 'signup',
  wageringRequirement: 'low',
  wageringMultiplier: 30,
  countries: ['US', 'CA'],
  features: ['Feature 1', 'Feature 2'],
  rating: 4.5,
  popularity: 80,
  description: 'Test bonus description',
  terms: ['Term 1', 'Term 2'],
  logo: '🎰',
  isActive: true,
  lastVerified: new Date(),
  minDeposit: 10,
  gameContribution: { slots: 100, tableGames: 50, liveDealer: 50 },
};

describe('BonusCard', () => {
  it('renders the casino name and bonus offer', () => {
    render(
      <BonusProvider>
        <BonusCard bonus={mockBonus} />
      </BonusProvider>
    );
    expect(screen.getByText('Test Casino')).toBeInTheDocument();
    expect(screen.getByText('100% up to $100')).toBeInTheDocument();
  });
}); 