using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using DG.Tweening;

public class ramune : MonoBehaviour
{
    public Transform[] indexFinger;
    public Transform[] indexFinger2;
    public Transform[] indexFinger3;
    public Transform rightHand;
    
    void Start()
    {
        Sequence sequence = DOTween.Sequence();

        foreach (Transform finger in indexFinger)
        {
            sequence.Join(
                finger.DOLocalRotate(new Vector3(60,0,0), 0.5f)
            );
        }
        foreach (Transform finger2 in indexFinger2)
        {
            sequence.Join(
                finger2.DOLocalRotate(new Vector3(60,0,0), 0.5f)
            );
        }

        Vector3[] angles =
        {
            new Vector3(0, -100, -50),
            new Vector3(40, 0, 0),
            new Vector3(0, 90, 90),
            new Vector3(30, 0, 0)
        }; 
        for (int i = 0; i < indexFinger3.Length; i++)
        {
            sequence.Join(
                indexFinger3[i].DOLocalRotate(angles[i], 0.5f)
            );
        }

        sequence.AppendInterval(1.0f);

        sequence.Join(
            rightHand.DOMove(rightHand.position + new Vector3(-0.4f, 0.1f, 0.1f), 1.0f)
        );
        sequence.Join(
            rightHand.DOLocalRotate(new Vector3(-90, 0, -90), 1.0f)
        );

        sequence.AppendInterval(1.0f);

        sequence.Append(
            rightHand.DOMoveY(rightHand.position.y + 0.05f, 0.5f)
        );

        sequence.AppendInterval(0.5f);

        sequence.Append(
            rightHand.DOMoveY(rightHand.position.y + 0.05f + 0.05f, 0.5f)
        );

        sequence.AppendInterval(0.5f);

        sequence.Join(
            rightHand.DOMove(rightHand.position + new Vector3(0.01f, 0, 0), 1.0f)
        );
        sequence.Join(
            rightHand.DOLocalRotate(new Vector3(0, 90, 180), 1.0f)
        );
    }

    // Update is called once per frame
    void Update()
    {
        
    }
}
