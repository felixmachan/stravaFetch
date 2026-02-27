import { Mountain, PlusCircle } from './icons';
import { Link } from 'react-router-dom';
import { Button } from './button';
import { Card } from './card';

export function EmptyState() {
  return (
    <Card className='bg-gradient-to-r from-emerald-500/10 to-cyan-500/10'>
      <div className='flex flex-col gap-3 md:flex-row md:items-center md:justify-between'>
        <div>
          <p className='text-lg font-semibold'>No activities yet</p>
          <p className='text-sm text-muted-foreground'>Connect Strava or import demo data to unlock analytics and coaching insights.</p>
        </div>
        <div className='flex gap-2'>
          <Link to='/settings'>
            <Button variant='outline'>
              <Mountain className='h-4 w-4' />
              Connect Strava
            </Button>
          </Link>
          <Link to='/settings?demo=1'>
            <Button>
              <PlusCircle className='h-4 w-4' />
              Import Demo Activity
            </Button>
          </Link>
        </div>
      </div>
    </Card>
  );
}
