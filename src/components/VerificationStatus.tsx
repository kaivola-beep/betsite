import React from 'react';
import { CheckCircle, AlertTriangle, Clock, XCircle } from 'lucide-react';

interface VerificationStatusProps {
  isActive: boolean;
  lastVerified: Date;
  expiresAt?: Date;
  size?: 'sm' | 'md';
}

const VerificationStatus: React.FC<VerificationStatusProps> = ({ 
  isActive, 
  lastVerified, 
  expiresAt,
  size = 'md'
}) => {
  const now = new Date();
  const timeSinceVerified = now.getTime() - lastVerified.getTime();
  const hoursAgo = Math.floor(timeSinceVerified / (1000 * 60 * 60));
  const minutesAgo = Math.floor(timeSinceVerified / (1000 * 60));
  
  const getTimeAgoText = () => {
    if (hoursAgo >= 24) {
      const daysAgo = Math.floor(hoursAgo / 24);
      return `${daysAgo}d ago`;
    } else if (hoursAgo >= 1) {
      return `${hoursAgo}h ago`;
    } else {
      return `${minutesAgo}m ago`;
    }
  };

  const getExpiryText = () => {
    if (!expiresAt) return null;
    
    const timeUntilExpiry = expiresAt.getTime() - now.getTime();
    const daysUntilExpiry = Math.floor(timeUntilExpiry / (1000 * 60 * 60 * 24));
    
    if (daysUntilExpiry <= 0) return 'Expired';
    if (daysUntilExpiry === 1) return 'Expires tomorrow';
    if (daysUntilExpiry <= 7) return `${daysUntilExpiry} days left`;
    return `${daysUntilExpiry} days left`;
  };

  const getStatusConfig = () => {
    if (!isActive) {
      return {
        icon: XCircle,
        color: 'text-red-600',
        bg: 'bg-red-50',
        border: 'border-red-200',
        text: 'Inactive',
        description: 'Bonus currently unavailable'
      };
    }

    const isStale = hoursAgo >= 6;
    const isExpiringSoon = expiresAt && (expiresAt.getTime() - now.getTime()) <= (3 * 24 * 60 * 60 * 1000);

    if (isExpiringSoon) {
      return {
        icon: AlertTriangle,
        color: 'text-orange-600',
        bg: 'bg-orange-50',
        border: 'border-orange-200',
        text: 'Expiring Soon',
        description: getExpiryText()
      };
    }

    if (isStale) {
      return {
        icon: Clock,
        color: 'text-yellow-600',
        bg: 'bg-yellow-50',
        border: 'border-yellow-200',
        text: 'Needs Verification',
        description: `Last checked ${getTimeAgoText()}`
      };
    }

    return {
      icon: CheckCircle,
      color: 'text-green-600',
      bg: 'bg-green-50',
      border: 'border-green-200',
      text: 'Verified Active',
      description: `Checked ${getTimeAgoText()}`
    };
  };

  const status = getStatusConfig();
  const Icon = status.icon;
  
  const sizeClasses = size === 'sm' 
    ? 'px-2 py-1 text-xs' 
    : 'px-3 py-2 text-sm';

  return (
    <div className={`inline-flex items-center space-x-2 ${status.bg} ${status.border} border rounded-full ${sizeClasses}`}>
      <Icon size={size === 'sm' ? 12 : 16} className={status.color} />
      <div className="flex flex-col">
        <span className={`font-medium ${status.color}`}>
          {status.text}
        </span>
        {size === 'md' && (
          <span className="text-xs text-slate-500">
            {status.description}
          </span>
        )}
      </div>
    </div>
  );
};

export default VerificationStatus;