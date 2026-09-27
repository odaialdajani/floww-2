import React, {useState} from 'react';

const ITEMS = ['Checked quote age and missing fields', 'Checked option side, strike and expiry',
  'Reviewed volume and open interest', 'Reviewed the chart and available history',
  'Considered spread and exit costs', 'Set my risk limit'];

export default function ContractReview({contractKey}) {
  const [reviews, setReviews] = useState({});
  if (!contractKey) return null;
  const review = reviews[contractKey] || {checks: {}, status: ''};
  const update = changes => setReviews(previous => ({...previous,
    [contractKey]: {...(previous[contractKey] || {checks: {}, status: ''}), ...changes}}));
  return <details className="th-disc" data-testid="contract-review">
    <summary>My review (this visit)</summary>
    <p>Manual notes only. These checks do not verify the data or approve a trade.</p>
    {ITEMS.map((label, index) => <label key={label} style={{display:'block'}}>
      <input type="checkbox" checked={!!review.checks[index]}
        onChange={() => update({checks: {...review.checks, [index]: !review.checks[index]}, status:''})}/>{' '}{label}
    </label>)}
    <button type="button" className="th-chipb" onClick={() => update({status:'Reviewed'})}>Mark reviewed</button>
    <button type="button" className="th-chipb" onClick={() => update({status:'Skipped'})}>Skip review</button>
    {review.status && <span role="status">{review.status}</span>}
  </details>;
}
