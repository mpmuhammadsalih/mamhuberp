import { QueryClientProvider } from '@tanstack/react-query'
import { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ScrollToTop } from './components/layout/ScrollToTop'
import { StorefrontShell } from './components/layout/StorefrontShell'
import { StorefrontLogoProvider } from './context/StorefrontLogoContext'
import { LocaleProvider, useLocale } from './i18n/LocaleContext'
import { HomePage } from './pages/HomePage'
import { ProductsPage } from './pages/ProductsPage'
import { CartPage } from './pages/CartPage'
import { LoginPage } from './pages/LoginPage'
import { bootstrapCustomerSession } from './lib/session'
import { queryClient } from './lib/queryClient'
import { collectionQuery, prefetchCatalogMetadata } from './lib/queries/catalog'
import { prefetchCmsPages } from './lib/queries/cms'
import { preloadStorefrontImages } from './lib/queries/preloadStorefrontImages'
import { storefrontQueries } from './lib/queries/storefront'

const CollectionPage = lazy(() => import('./pages/CollectionPage').then((m) => ({ default: m.CollectionPage })))
const CheckoutPage = lazy(() => import('./pages/CheckoutPage').then((m) => ({ default: m.CheckoutPage })))
const ProductDetailPage = lazy(() => import('./pages/ProductDetailPage').then((m) => ({ default: m.ProductDetailPage })))
const GiftFinderPage = lazy(() => import('./pages/GiftFinderPage').then((m) => ({ default: m.GiftFinderPage })))
const ProfilePage = lazy(() => import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const OrdersPage = lazy(() => import('./pages/OrdersPage').then((m) => ({ default: m.OrdersPage })))
const OrderDetailPage = lazy(() => import('./pages/OrderDetailPage').then((m) => ({ default: m.OrderDetailPage })))
const OrderSuccessPage = lazy(() => import('./pages/OrderSuccessPage').then((m) => ({ default: m.OrderSuccessPage })))
const PaymentReturnPage = lazy(() => import('./pages/PaymentReturnPage').then((m) => ({ default: m.PaymentReturnPage })))
const WishlistPage = lazy(() => import('./pages/WishlistPage').then((m) => ({ default: m.WishlistPage })))
const InboxPage = lazy(() => import('./pages/InboxPage').then((m) => ({ default: m.InboxPage })))
const AddressesPage = lazy(() => import('./pages/AddressesPage').then((m) => ({ default: m.AddressesPage })))
const LoyaltyPage = lazy(() => import('./pages/LoyaltyPage').then((m) => ({ default: m.LoyaltyPage })))
const CmsPage = lazy(() => import('./pages/CmsPage').then((m) => ({ default: m.CmsPage })))
const ForgotPasswordPage = lazy(() => import('./pages/ForgotPasswordPage').then((m) => ({ default: m.ForgotPasswordPage })))
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage').then((m) => ({ default: m.ResetPasswordPage })))

function PageLoader() {
  const { t } = useLocale()
  return <div className="py-16 text-center font-catalog text-slate-500">{t.common.loading}</div>
}

function StorefrontRoutes() {
  useEffect(() => {
    prefetchCatalogMetadata(queryClient)
    prefetchCmsPages(queryClient)
    void queryClient.prefetchQuery(storefrontQueries.home).then(() => {
      preloadStorefrontImages(queryClient.getQueryData(storefrontQueries.home.queryKey))
    })
    void queryClient.prefetchQuery(collectionQuery('new-arrivals', 1, 6))
    void queryClient.prefetchQuery(collectionQuery('best-sellers', 1, 8))
    void queryClient.prefetchQuery(collectionQuery('offers', 1, 8))
    void bootstrapCustomerSession().then((restored) => {
      if (restored) {
        queryClient.invalidateQueries({ queryKey: ['profile'] })
        queryClient.invalidateQueries({ queryKey: ['wishlist'] })
      }
    })
  }, [])

  return (
    <StorefrontShell>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/offers" element={<CollectionPage />} />
          <Route path="/new-arrivals" element={<CollectionPage />} />
          <Route path="/best-sellers" element={<CollectionPage />} />
          <Route path="/featured" element={<CollectionPage />} />
          <Route path="/collections/:collection" element={<CollectionPage />} />
          <Route path="/products/:itemCode" element={<ProductDetailPage />} />
          <Route path="/cart" element={<CartPage />} />
          <Route path="/checkout" element={<CheckoutPage />} />
          <Route path="/checkout/payment/return" element={<PaymentReturnPage />} />
          <Route path="/order-success/:orderId" element={<OrderSuccessPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/orders/:orderId" element={<OrderDetailPage />} />
          <Route path="/wishlist" element={<WishlistPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/loyalty" element={<LoyaltyPage />} />
          <Route path="/gift-finder" element={<GiftFinderPage />} />
          <Route path="/addresses" element={<AddressesPage />} />
          <Route path="/page/:slug" element={<CmsPage />} />
        </Routes>
      </Suspense>
    </StorefrontShell>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <LocaleProvider>
        <StorefrontLogoProvider>
          <BrowserRouter>
            <ScrollToTop />
            <Routes>
              <Route path="/admin/*" element={<Navigate to="/" replace />} />
              <Route path="/*" element={<StorefrontRoutes />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </StorefrontLogoProvider>
      </LocaleProvider>
    </QueryClientProvider>
  )
}

export default App
