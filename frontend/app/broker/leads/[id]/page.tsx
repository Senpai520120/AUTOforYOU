import BrokerLeadCard from '@/components/leads/BrokerLeadCard';

export const dynamic = 'force-dynamic';

type Props = { params: Promise<{ id: string }> };

export default async function BrokerLeadPage({ params }: Props) {
  const { id } = await params;
  return <BrokerLeadCard id={Number(id)} />;
}
