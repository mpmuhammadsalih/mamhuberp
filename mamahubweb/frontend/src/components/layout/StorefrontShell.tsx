import { lazy, Suspense, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

import { Footer } from '../Footer'
import { Header } from '../Header'
import { InboxAlertPopup } from '../InboxAlertPopup'
import { InboxWidget } from '../InboxWidget'
import { WhatsAppChatButton } from '../WhatsAppChatButton'
import { InboxWidgetProvider } from '../../context/InboxWidgetContext'
import { CategoryNavBar } from '../catalog/CategoryNavBar'
import { DeliveryLocationProvider } from '../../context/DeliveryLocationContext'
import { MobileBottomNav } from './MobileBottomNav'
import { ToyRainbowBar } from './ToyRainbowBar'

const LocationPickerDrawer = lazy(() =>
  import('../delivery/LocationPickerDrawer').then((m) => ({ default: m.LocationPickerDrawer })),
)

interface Props {
  children: ReactNode
}

const MINIMAL_CHROME_ROUTES = ['/checkout', '/order-success', '/login']

export function StorefrontShell({ children }: Props) {
  const { pathname } = useLocation()
  const minimalChrome = MINIMAL_CHROME_ROUTES.some((route) => pathname.startsWith(route))

  return (
    <DeliveryLocationProvider>
      <InboxWidgetProvider>
      <div className={`storefront-shell min-h-screen ${minimalChrome ? '' : 'has-mobile-nav'}`}>
        <div className="sticky top-0 z-[60] isolate overflow-visible bg-white shadow-[0_1px_8px_rgba(15,23,42,0.06)]">
          <Header />
          <CategoryNavBar />
          <ToyRainbowBar />
        </div>
        <Suspense fallback={null}>
          <LocationPickerDrawer />
        </Suspense>
        <main className="storefront-main bg-brand-cream">{children}</main>
        {!minimalChrome && (
          <div className="pb-[calc(5.5rem+env(safe-area-inset-bottom,0px))] md:pb-0">
            <Footer />
          </div>
        )}
        {!minimalChrome && <MobileBottomNav />}
        <WhatsAppChatButton aboveMobileNav={!minimalChrome} />
        <InboxWidget aboveMobileNav={!minimalChrome} hideLauncher={minimalChrome} />
        <InboxAlertPopup />
      </div>
      </InboxWidgetProvider>
    </DeliveryLocationProvider>
  )
}
