import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { PAGE_CONTAINER } from '../components/layout/homeLayout'
import { useLocale } from '../i18n/LocaleContext'
import { useFormatMoney } from '../i18n/useFormatMoney'
import { getData } from '../lib/api'
import { storage } from '../lib/storage'

interface LoyaltyDashboard {
  account: {
    membership_number: string
    points_balance: number
    lifetime_points: number
    tier_code?: string
    tier_name?: string
  }
  rule: {
    earn_spend_amount: number
    earn_points: number
    redeem_points: number
    redeem_value: number
    min_redeem_points: number
    max_redeem_percent: number
  }
  tiers: Array<{ tier_code: string; tier_name: string; min_lifetime_points: number }>
  next_tier?: { tier_name: string; min_lifetime_points: number }
  transactions: Array<{
    transaction_id: number
    transaction_type: string
    points: number
    description?: string
    created_at?: string
  }>
}

export function LoyaltyPage() {
  const { t } = useLocale()
  const formatMoney = useFormatMoney()

  const { data, isLoading } = useQuery({
    queryKey: ['loyalty'],
    queryFn: () => getData<LoyaltyDashboard>('/loyalty/dashboard'),
    enabled: storage.hasSession(),
  })

  if (!storage.hasSession()) {
    return (
      <div className={`${PAGE_CONTAINER} py-12 text-center`}>
        <p className="text-gray-600">{t.account.signInLoyalty}</p>
        <Link to="/login" className="mt-4 inline-block text-brand-accent hover:underline">
          {t.auth.signIn}
        </Link>
      </div>
    )
  }

  if (isLoading || !data) {
    return <div className={`${PAGE_CONTAINER} py-12`}>{t.account.loadingLoyalty}</div>
  }

  const { account, rule, tiers, next_tier, transactions } = data

  return (
    <div className={`${PAGE_CONTAINER} py-8`}>
      <h1 className="mb-2 text-3xl font-bold">{t.account.loyaltyRewards}</h1>
      <p className="mb-8 text-gray-500">Member #{account.membership_number}</p>

      <div className="mb-8 grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl bg-gradient-to-br from-brand-accent to-brand-accent-hover p-6 text-white shadow-lg">
          <p className="text-sm opacity-90">{t.account.availablePoints}</p>
          <p className="text-4xl font-bold">{account.points_balance}</p>
          <p className="mt-2 text-sm">{account.tier_name || account.tier_code || 'Bronze'} member</p>
        </div>
        <div className="rounded-2xl bg-white p-6 shadow-sm">
          <p className="text-sm text-gray-500">{t.account.lifetimePoints}</p>
          <p className="text-2xl font-bold">{account.lifetime_points}</p>
        </div>
        <div className="rounded-2xl bg-white p-6 shadow-sm">
          <p className="text-sm text-gray-500">{t.account.howYouEarn}</p>
          <p className="mt-1 text-sm">
            {rule.earn_points} point per {formatMoney(rule.earn_spend_amount)} spent
          </p>
          <p className="mt-2 text-sm text-gray-600">
            Redeem {rule.redeem_points} pts = {formatMoney(rule.redeem_value)}
          </p>
        </div>
      </div>

      {next_tier && (
        <p className="mb-6 text-sm text-gray-600">
          {next_tier.min_lifetime_points - account.lifetime_points} points until{' '}
          <strong>{next_tier.tier_name}</strong>
        </p>
      )}

      <section className="mb-8">
        <h2 className="mb-4 text-xl font-bold">{t.account.membershipTiers}</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {tiers.map((tier) => (
            <div
              key={tier.tier_code}
              className={`rounded-xl p-4 text-center ${
                tier.tier_code === account.tier_code
                  ? 'bg-pink-100 ring-2 ring-brand-accent'
                  : 'bg-white shadow-sm'
              }`}
            >
              <p className="font-semibold">{tier.tier_name}</p>
              <p className="text-xs text-gray-500">{tier.min_lifetime_points}+ pts</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-bold">{t.account.recentActivity}</h2>
        <ul className="space-y-3">
          {transactions.map((tx) => (
            <li key={tx.transaction_id} className="flex justify-between rounded-xl bg-white p-4 shadow-sm">
              <div>
                <p className="font-medium">{tx.transaction_type}</p>
                <p className="text-sm text-gray-500">{tx.description}</p>
              </div>
              <span className={tx.points >= 0 ? 'text-green-600' : 'text-red-600'}>
                {tx.points >= 0 ? '+' : ''}
                {tx.points}
              </span>
            </li>
          ))}
          {!transactions.length && <li className="text-gray-500">{t.account.noActivity}</li>}
        </ul>
      </section>
    </div>
  )
}
