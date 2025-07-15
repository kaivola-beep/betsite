import React, { useState } from 'react';
import { Calculator, TrendingUp, AlertTriangle, CheckCircle, DollarSign } from 'lucide-react';
import { Bonus } from '../context/BonusContext';

interface BonusCalculatorProps {
  bonus: Bonus;
  isOpen: boolean;
  onClose: () => void;
}

const BonusCalculator: React.FC<BonusCalculatorProps> = ({ bonus, isOpen, onClose }) => {
  const [depositAmount, setDepositAmount] = useState(bonus.minDeposit);
  const [gameType, setGameType] = useState<'slots' | 'tableGames' | 'liveDealer'>('slots');
  const [averageBetSize, setAverageBetSize] = useState(5);

  if (!isOpen) return null;

  // Calculate bonus amount
  const bonusAmount = Math.min(depositAmount * (bonus.bonusType === 'signup' ? 2 : 0.5), bonus.bonusValue);
  
  // Calculate total wagering requirement
  const totalWageringRequired = (depositAmount + bonusAmount) * bonus.wageringMultiplier;
  
  // Calculate effective wagering based on game contribution
  const gameContribution = bonus.gameContribution[gameType] / 100;
  const effectiveWageringRequired = totalWageringRequired / gameContribution;
  
  // Calculate number of bets needed
  const betsNeeded = Math.ceil(effectiveWageringRequired / averageBetSize);
  
  // Calculate expected loss (house edge estimates)
  const houseEdge = gameType === 'slots' ? 0.05 : gameType === 'tableGames' ? 0.02 : 0.015;
  const expectedLoss = effectiveWageringRequired * houseEdge;
  
  // Calculate net expected value
  const netExpectedValue = bonusAmount - expectedLoss;
  
  // Calculate time estimate (assuming 10 bets per minute)
  const estimatedTimeMinutes = betsNeeded / 10;
  const estimatedHours = Math.floor(estimatedTimeMinutes / 60);
  const estimatedMinutes = Math.floor(estimatedTimeMinutes % 60);

  const getRiskLevel = () => {
    if (bonus.wageringMultiplier === 0) return { level: 'Low', color: 'text-green-600', bg: 'bg-green-50' };
    if (bonus.wageringMultiplier <= 35) return { level: 'Medium', color: 'text-yellow-600', bg: 'bg-yellow-50' };
    return { level: 'High', color: 'text-red-600', bg: 'bg-red-50' };
  };

  const risk = getRiskLevel();

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-slate-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Calculator className="text-emerald-600" size={24} />
              <h3 className="text-xl font-bold text-slate-900">Bonus Calculator</h3>
            </div>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-600 text-2xl"
            >
              ×
            </button>
          </div>
          <p className="text-slate-600 mt-2">{bonus.casinoName} - {bonus.bonusOffer}</p>
        </div>

        <div className="p-6 space-y-6">
          {/* Input Controls */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Deposit Amount ($)
              </label>
              <input
                type="number"
                value={depositAmount}
                onChange={(e) => setDepositAmount(Number(e.target.value))}
                min={bonus.minDeposit}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              />
              <p className="text-xs text-slate-500 mt-1">Min: ${bonus.minDeposit}</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Game Type
              </label>
              <select
                value={gameType}
                onChange={(e) => setGameType(e.target.value as any)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              >
                <option value="slots">Slots ({bonus.gameContribution.slots}%)</option>
                <option value="tableGames">Table Games ({bonus.gameContribution.tableGames}%)</option>
                <option value="liveDealer">Live Dealer ({bonus.gameContribution.liveDealer}%)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Average Bet Size ($)
              </label>
              <input
                type="number"
                value={averageBetSize}
                onChange={(e) => setAverageBetSize(Number(e.target.value))}
                min={0.1}
                step={0.1}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
              />
            </div>
          </div>

          {/* Risk Assessment */}
          <div className={`p-4 rounded-lg ${risk.bg}`}>
            <div className="flex items-center space-x-2 mb-2">
              <AlertTriangle className={risk.color} size={20} />
              <span className={`font-semibold ${risk.color}`}>Risk Level: {risk.level}</span>
            </div>
            <p className="text-sm text-slate-600">
              {bonus.wageringMultiplier === 0 
                ? 'No wagering requirements - you can withdraw immediately!'
                : `${bonus.wageringMultiplier}x wagering requirement applies to bonus + deposit amount.`
              }
            </p>
          </div>

          {/* Calculation Results */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-slate-50 p-4 rounded-lg">
              <h4 className="font-semibold text-slate-900 mb-3">Bonus Breakdown</h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-600">Your deposit:</span>
                  <span className="font-medium">${depositAmount}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600">Bonus amount:</span>
                  <span className="font-medium text-emerald-600">${bonusAmount}</span>
                </div>
                <div className="flex justify-between border-t border-slate-200 pt-2">
                  <span className="text-slate-600">Total to play with:</span>
                  <span className="font-bold">${depositAmount + bonusAmount}</span>
                </div>
              </div>
            </div>

            <div className="bg-slate-50 p-4 rounded-lg">
              <h4 className="font-semibold text-slate-900 mb-3">Wagering Requirements</h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-600">Must wager:</span>
                  <span className="font-medium">${totalWageringRequired.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600">Effective wagering:</span>
                  <span className="font-medium">${effectiveWageringRequired.toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-600">Bets needed:</span>
                  <span className="font-medium">{betsNeeded.toLocaleString()}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Expected Value Analysis */}
          <div className="bg-gradient-to-r from-emerald-50 to-teal-50 p-4 rounded-lg border border-emerald-200">
            <h4 className="font-semibold text-slate-900 mb-3 flex items-center space-x-2">
              <TrendingUp className="text-emerald-600" size={20} />
              <span>Expected Value Analysis</span>
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div className="text-center">
                <div className="text-2xl font-bold text-emerald-600">${bonusAmount}</div>
                <div className="text-slate-600">Bonus Value</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-red-600">-${expectedLoss.toFixed(2)}</div>
                <div className="text-slate-600">Expected Loss</div>
              </div>
              <div className="text-center">
                <div className={`text-2xl font-bold ${netExpectedValue > 0 ? 'text-green-600' : 'text-red-600'}`}>
                  ${netExpectedValue.toFixed(2)}
                </div>
                <div className="text-slate-600">Net Expected Value</div>
              </div>
            </div>
          </div>

          {/* Time Estimate */}
          <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
            <h4 className="font-semibold text-slate-900 mb-2">Estimated Completion Time</h4>
            <div className="flex items-center space-x-2">
              <CheckCircle className="text-blue-600" size={20} />
              <span className="text-slate-700">
                Approximately {estimatedHours > 0 && `${estimatedHours}h `}{estimatedMinutes}m of active play
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Based on 10 bets per minute average
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex space-x-3 pt-4 border-t border-slate-200">
            <button
              onClick={onClose}
              className="flex-1 bg-emerald-600 text-white py-3 px-4 rounded-lg font-semibold hover:bg-emerald-700 transition-colors flex items-center justify-center space-x-2"
            >
              <DollarSign size={20} />
              <span>Claim This Bonus</span>
            </button>
            <button
              onClick={onClose}
              className="px-6 py-3 border border-slate-300 text-slate-700 rounded-lg font-medium hover:bg-slate-50 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BonusCalculator;