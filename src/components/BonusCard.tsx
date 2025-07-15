import React, { useState } from 'react';
import { Star, Bookmark, BookmarkCheck, ExternalLink, Info, Globe, Shield, Calculator } from 'lucide-react';
import { useBonusContext, Bonus } from '../context/BonusContext';
import BonusCalculator from './BonusCalculator';
import VerificationStatus from './VerificationStatus';
import { getWageringColor, getWageringText } from '../utils/bonusUtils';

interface BonusCardProps {
  bonus: Bonus;
}

interface BonusCardHeaderProps {
  bonus: Bonus;
  isSaved: boolean;
  toggleSavedBonus: (id: string) => void;
}
const BonusCardHeader: React.FC<BonusCardHeaderProps> = ({ bonus, isSaved, toggleSavedBonus }: BonusCardHeaderProps) => (
  <div className="flex items-start justify-between mb-4">
    <div className="flex items-center space-x-3">
      <div className="text-3xl">{bonus.logo}</div>
      <div>
        <h3 className="font-bold text-slate-900 text-lg">{bonus.casinoName}</h3>
        <div className="flex items-center space-x-2 mt-1">
          <div className="flex items-center space-x-1">
            {[...Array(5)].map((_, i) => (
              <Star
                key={i}
                size={14}
                className={i < Math.floor(bonus.rating) ? 'text-yellow-400 fill-current' : 'text-slate-300'}
              />
            ))}
          </div>
          <span className="text-sm text-slate-600">{bonus.rating}</span>
        </div>
      </div>
    </div>
    <button
      onClick={() => toggleSavedBonus(bonus.id)}
      className={`p-2 rounded-lg transition-colors ${
        isSaved 
          ? 'bg-emerald-100 text-emerald-600 hover:bg-emerald-200' 
          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
      }`}
      aria-label={isSaved ? 'Remove from saved bonuses' : 'Save bonus'}
    >
      {isSaved ? <BookmarkCheck size={20} /> : <Bookmark size={20} />}
    </button>
  </div>
);

interface BonusCardFeaturesProps {
  bonus: Bonus;
}
const BonusCardFeatures: React.FC<BonusCardFeaturesProps> = ({ bonus }: BonusCardFeaturesProps) => (
  <div className="flex flex-wrap gap-2 mb-4">
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getWageringColor(bonus.wageringRequirement)}`}>
      {getWageringText(bonus.wageringRequirement)}
    </span>
    {bonus.features.slice(0, 2).map((feature, index) => (
      <span key={index} className="px-2 py-1 bg-slate-100 text-slate-700 rounded-full text-xs font-medium">
        {feature}
      </span>
    ))}
    {bonus.features.length > 2 && (
      <span className="px-2 py-1 bg-slate-100 text-slate-700 rounded-full text-xs font-medium">
        +{bonus.features.length - 2} more
      </span>
    )}
  </div>
);

interface BonusCardCountriesProps {
  bonus: Bonus;
}
const BonusCardCountries: React.FC<BonusCardCountriesProps> = ({ bonus }: BonusCardCountriesProps) => (
  <div className="flex items-center space-x-2 mb-4">
    <Globe size={16} className="text-slate-400" />
    <span className="text-sm text-slate-600">
      Available in: {bonus.countries.slice(0, 3).join(', ')}
      {bonus.countries.length > 3 && ` +${bonus.countries.length - 3} more`}
    </span>
  </div>
);

interface BonusCardActionsProps {
  bonus: Bonus;
  isActive: boolean;
  setShowCalculator: (show: boolean) => void;
  showDetails: boolean;
  setShowDetails: (show: boolean) => void;
}
const BonusCardActions: React.FC<BonusCardActionsProps> = ({ bonus, isActive, setShowCalculator, showDetails, setShowDetails }: BonusCardActionsProps) => (
  <div className="px-6 pb-4">
    <div className="flex space-x-3 mb-3">
      <button 
        disabled={!isActive}
        className={`flex-1 py-3 px-4 rounded-lg font-semibold transition-colors flex items-center justify-center space-x-2 ${
          isActive 
            ? 'bg-emerald-600 text-white hover:bg-emerald-700' 
            : 'bg-slate-300 text-slate-500 cursor-not-allowed'
        }`}
        aria-label="Claim Bonus"
      >
        <span>Claim Bonus</span>
        <ExternalLink size={16} />
      </button>
      <button 
        onClick={() => setShowCalculator(true)}
        className="px-4 py-3 border border-emerald-300 text-emerald-700 rounded-lg font-medium hover:bg-emerald-50 transition-colors flex items-center space-x-1"
        aria-label="Open Bonus Calculator"
      >
        <Calculator size={16} />
        <span className="hidden sm:inline">Calculate</span>
      </button>
    </div>
    <button
      onClick={() => setShowDetails(!showDetails)}
      className="w-full flex items-center justify-center space-x-2 text-sm text-slate-600 hover:text-slate-900 transition-colors"
      aria-label={showDetails ? 'Hide Details' : 'Show Details'}
    >
      <Info size={16} />
      <span>{showDetails ? 'Hide' : 'Show'} Details</span>
    </button>
  </div>
);

interface BonusCardDetailsProps {
  bonus: Bonus;
}
const BonusCardDetails: React.FC<BonusCardDetailsProps> = ({ bonus }: BonusCardDetailsProps) => (
  <div className="border-t border-slate-200 p-6 bg-slate-50">
    <h4 className="font-semibold text-slate-900 mb-3 flex items-center space-x-2">
      <Shield size={16} />
      <span>Terms & Conditions</span>
    </h4>
    <ul className="space-y-2">
      {bonus.terms.map((term, index) => (
        <li key={index} className="text-sm text-slate-600 flex items-start space-x-2">
          <span className="w-1.5 h-1.5 bg-slate-400 rounded-full mt-2 flex-shrink-0" />
          <span>{term}</span>
        </li>
      ))}
    </ul>
    <div className="mt-4 pt-4 border-t border-slate-200">
      <h5 className="font-medium text-slate-900 mb-2">All Features:</h5>
      <div className="flex flex-wrap gap-2">
        {bonus.features.map((feature, index) => (
          <span key={index} className="px-2 py-1 bg-white border border-slate-200 text-slate-700 rounded-full text-xs">
            {feature}
          </span>
        ))}
      </div>
    </div>
  </div>
);

const BonusCard: React.FC<BonusCardProps> = ({ bonus }) => {
  const { savedBonuses, toggleSavedBonus } = useBonusContext();
  const [showDetails, setShowDetails] = useState(false);
  const [showCalculator, setShowCalculator] = useState(false);
  const isSaved = savedBonuses.includes(bonus.id);

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-all duration-300 overflow-hidden">
      <div className="p-6 pb-4">
        <BonusCardHeader bonus={bonus} isSaved={isSaved} toggleSavedBonus={toggleSavedBonus} />
        <div className="bg-gradient-to-r from-emerald-50 to-teal-50 rounded-lg p-4 mb-4">
          <div className="flex items-center justify-between mb-2">
            <VerificationStatus 
              isActive={bonus.isActive}
              lastVerified={bonus.lastVerified}
              expiresAt={bonus.expiresAt}
              size="sm"
            />
            {bonus.expiresAt && (
              <div className="text-xs text-slate-500">
                Expires {bonus.expiresAt.toLocaleDateString()}
              </div>
            )}
          </div>
          <div className="text-lg font-bold text-slate-900 mb-1">
            {bonus.bonusOffer}
          </div>
          <div className="text-sm text-slate-600">
            {bonus.description}
          </div>
        </div>
        <BonusCardFeatures bonus={bonus} />
        <BonusCardCountries bonus={bonus} />
      </div>
      <BonusCardActions 
        bonus={bonus} 
        isActive={bonus.isActive} 
        setShowCalculator={setShowCalculator} 
        showDetails={showDetails} 
        setShowDetails={setShowDetails} 
      />
      {showDetails && <BonusCardDetails bonus={bonus} />}
      <BonusCalculator 
        bonus={bonus}
        isOpen={showCalculator}
        onClose={() => setShowCalculator(false)}
      />
    </div>
  );
};

export default BonusCard